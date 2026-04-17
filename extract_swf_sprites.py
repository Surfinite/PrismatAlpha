"""Extract sprite sheet images from decompressed SWF and crop individual sprites."""
import struct
import zlib
import io
import os
from PIL import Image

SWF_PATH = "prismata_decompressed.swf"
OUTPUT_DIR = "bin/asset/images/icons/extracted_hd"

# HD atlas coordinates from GameAsset_xmlHDData (1564x465 sprite sheet)
HD_SPRITES = {
    "shield_big":        (1140, 90, 108, 108),
    "shield_big_broken": (1140, 200, 108, 108),
    "shield_big_glow":   (1356, 166, 108, 108),
    "sword_big":         (1454, 2, 108, 108),
    "sword_big_glow":    (1389, 336, 108, 108),
    "interro":           (1290, 366, 97, 97),   # breach warning "!!"
    "interro2":          (1250, 166, 97, 97),   # wipeout warning
    "tap_big":           (1510, 112, 47, 47),   # chill/tap icon
    "sword":             (2, 2, 461, 461),      # large sword
}

# SD atlas coordinates for reference (511x431 sprite sheet)
SD_SPRITES = {
    "shield_big":        (378, 232, 60, 60),
    "sword_big":         (445, 2, 58, 58),
    "interro":           (437, 294, 54, 54),
}


def read_swf_tags(data):
    """Parse SWF tags from decompressed data."""
    # SWF header
    sig = data[0:3]
    version = data[3]
    file_length = struct.unpack_from('<I', data, 4)[0]

    # Parse RECT (variable-length bit field)
    nbits = (data[8] >> 3) & 0x1F
    rect_bits = 5 + nbits * 4
    rect_bytes = (rect_bits + 7) // 8
    offset = 8 + rect_bytes

    # Frame rate (2 bytes) + frame count (2 bytes)
    offset += 4

    tags = []
    while offset < len(data):
        if offset + 2 > len(data):
            break
        tag_code_and_length = struct.unpack_from('<H', data, offset)[0]
        offset += 2
        tag_type = tag_code_and_length >> 6
        tag_length = tag_code_and_length & 0x3F
        if tag_length == 0x3F:
            if offset + 4 > len(data):
                break
            tag_length = struct.unpack_from('<I', data, offset)[0]
            offset += 4
        tag_data = data[offset:offset + tag_length]
        tags.append((tag_type, tag_data))
        offset += tag_length
        if tag_type == 0:  # End tag
            break
    return tags


def extract_definebits_lossless2(tag_data):
    """Extract RGBA image from DefineBitsLossless2 (tag type 36)."""
    char_id = struct.unpack_from('<H', tag_data, 0)[0]
    fmt = tag_data[2]
    width = struct.unpack_from('<H', tag_data, 3)[0]
    height = struct.unpack_from('<H', tag_data, 5)[0]

    if fmt == 5:  # 32-bit ARGB
        compressed = tag_data[7:]
        decompressed = zlib.decompress(compressed)
        img = Image.new('RGBA', (width, height))
        pixels = []
        for i in range(0, len(decompressed), 4):
            if i + 3 >= len(decompressed):
                break
            a, r, g, b = decompressed[i], decompressed[i+1], decompressed[i+2], decompressed[i+3]
            pixels.append((r, g, b, a))
        img.putdata(pixels[:width * height])
        return char_id, width, height, img
    elif fmt == 3:  # 8-bit colormapped with alpha
        color_count = tag_data[7] + 1
        compressed = tag_data[8:]
        decompressed = zlib.decompress(compressed)
        # Color table: color_count * 4 bytes (RGBA)
        palette = []
        for i in range(color_count):
            off = i * 4
            r, g, b, a = decompressed[off], decompressed[off+1], decompressed[off+2], decompressed[off+3]
            palette.append((r, g, b, a))
        # Pixel data: rows padded to 4 bytes
        row_size = (width + 3) & ~3
        pixel_start = color_count * 4
        img = Image.new('RGBA', (width, height))
        pixels = []
        for row in range(height):
            row_offset = pixel_start + row * row_size
            for col in range(width):
                idx = decompressed[row_offset + col]
                pixels.append(palette[idx])
        img.putdata(pixels)
        return char_id, width, height, img
    return char_id, width, height, None


def extract_definebits_jpeg(tag_data, tag_type):
    """Extract image from DefineBitsJPEG2/3/4 tags."""
    char_id = struct.unpack_from('<H', tag_data, 0)[0]

    if tag_type == 21:  # DefineBitsJPEG2
        img_data = tag_data[2:]
    elif tag_type == 35:  # DefineBitsJPEG3
        alpha_offset = struct.unpack_from('<I', tag_data, 2)[0]
        img_data = tag_data[6:6 + alpha_offset]
        alpha_data = tag_data[6 + alpha_offset:]
    elif tag_type == 90:  # DefineBitsJPEG4
        alpha_offset = struct.unpack_from('<I', tag_data, 2)[0]
        img_data = tag_data[8:8 + alpha_offset]
        alpha_data = tag_data[8 + alpha_offset:]
    else:
        return char_id, 0, 0, None

    # Strip erroneous header if present
    if img_data[:4] == b'\xff\xd9\xff\xd8':
        img_data = img_data[4:]

    try:
        img = Image.open(io.BytesIO(img_data))
        img = img.convert('RGBA')

        # Apply alpha channel for JPEG3/4
        if tag_type in (35, 90) and alpha_data:
            try:
                alpha_decompressed = zlib.decompress(alpha_data)
                alpha_img = Image.frombytes('L', img.size, alpha_decompressed)
                r, g, b, _ = img.split()
                img = Image.merge('RGBA', (r, g, b, alpha_img))
            except Exception:
                pass

        return char_id, img.width, img.height, img
    except Exception as e:
        return char_id, 0, 0, None


def main():
    print(f"Reading SWF: {SWF_PATH}")
    with open(SWF_PATH, 'rb') as f:
        data = f.read()

    print(f"SWF size: {len(data)} bytes")
    tags = read_swf_tags(data)
    print(f"Found {len(tags)} tags")

    # Extract all images and find ones matching our target dimensions
    images = []
    target_hd = (1564, 465)  # HD atlas size
    target_sd = (511, 431)   # SD atlas size

    for tag_type, tag_data in tags:
        img = None
        char_id = 0
        w = h = 0

        if tag_type == 36:  # DefineBitsLossless2 (RGBA)
            char_id, w, h, img = extract_definebits_lossless2(tag_data)
        elif tag_type == 20:  # DefineBitsLossless (no alpha)
            # Similar to lossless2 but RGB
            pass
        elif tag_type in (21, 35, 90):  # DefineBitsJPEG2/3/4
            char_id, w, h, img = extract_definebits_jpeg(tag_data, tag_type)

        if img:
            images.append((char_id, w, h, img))
            if (w, h) == target_hd:
                print(f"  *** FOUND HD ATLAS: char_id={char_id}, {w}x{h}")
            elif (w, h) == target_sd:
                print(f"  *** FOUND SD ATLAS: char_id={char_id}, {w}x{h}")
            elif w > 400 or h > 400:
                print(f"  Large image: char_id={char_id}, {w}x{h}")

    print(f"\nExtracted {len(images)} images total")

    # Find and crop from HD atlas
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    hd_atlas = None
    sd_atlas = None
    for char_id, w, h, img in images:
        if (w, h) == target_hd:
            hd_atlas = img
        elif (w, h) == target_sd:
            sd_atlas = img

    if hd_atlas:
        print(f"\nCropping HD sprites from {hd_atlas.size} atlas:")
        hd_atlas.save(os.path.join(OUTPUT_DIR, "_atlas_HD.png"))
        for name, (x, y, w, h) in HD_SPRITES.items():
            sprite = hd_atlas.crop((x, y, x + w, y + h))
            path = os.path.join(OUTPUT_DIR, f"{name}.png")
            sprite.save(path)
            print(f"  {name}: {w}x{h} -> {path}")
    else:
        print("\nHD atlas not found! Dumping all large images for inspection...")
        for char_id, w, h, img in images:
            if w >= 100 or h >= 100:
                path = os.path.join(OUTPUT_DIR, f"_dump_{char_id}_{w}x{h}.png")
                img.save(path)
                print(f"  Dumped char_id={char_id} ({w}x{h})")

    if sd_atlas:
        print(f"\nCropping SD sprites from {sd_atlas.size} atlas:")
        sd_atlas.save(os.path.join(OUTPUT_DIR, "_atlas_SD.png"))
        for name, (x, y, w, h) in SD_SPRITES.items():
            sprite = sd_atlas.crop((x, y, x + w, y + h))
            path = os.path.join(OUTPUT_DIR, f"{name}_SD.png")
            sprite.save(path)
            print(f"  {name}: {w}x{h} -> {path}")


if __name__ == "__main__":
    main()
