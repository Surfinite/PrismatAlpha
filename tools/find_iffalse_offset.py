"""Find the iffalse byte offset for the DerpyMcLongName dummy game block in Prismata.swf"""

import zlib, struct, sys

def read_u30(data, offset):
    """Read AVM2 U30 (variable-length unsigned 30-bit integer)."""
    result = 0
    shift = 0
    for i in range(5):
        b = data[offset]
        offset += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    return result, offset

def encode_u30(value):
    """Encode a value as U30 bytes."""
    result = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            b |= 0x80
        result.append(b)
        if not value:
            break
    return bytes(result)

def main():
    swf_path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files (x86)\Steam\steamapps\common\Prismata\Prismata.swf"

    with open(swf_path, 'rb') as f:
        data = f.read()

    sig = data[:3]
    print(f"Signature: {sig}")

    if sig == b'CWS':
        body = zlib.decompress(data[8:])
    elif sig == b'FWS':
        body = data[8:]
    else:
        print("Unknown SWF format")
        return

    print(f"Decompressed body size: {len(body)} bytes")

    # Skip Rect header
    nbits = body[0] >> 3
    total_bits = 5 + 4 * nbits
    rect_bytes = (total_bits + 7) // 8
    # After Rect: FrameRate(UI16) + FrameCount(UI16) = 4 bytes
    tags_offset = rect_bytes + 4

    # Parse tags to find DoABC/DoABC2
    offset = tags_offset
    abc_found = None

    while offset < len(body) - 2:
        tag_val = struct.unpack_from('<H', body, offset)[0]
        tag_type = tag_val >> 6
        tag_length = tag_val & 0x3F
        offset += 2
        if tag_length == 0x3F:
            tag_length = struct.unpack_from('<I', body, offset)[0]
            offset += 4

        tag_data_offset = offset

        if tag_type in (72, 82):
            if tag_type == 82:
                name_end = body.index(b'\x00', tag_data_offset + 4)
                abc_data_offset = name_end + 1
            else:
                abc_data_offset = tag_data_offset

            abc_length = tag_length - (abc_data_offset - tag_data_offset)
            print(f"Found DoABC tag: ABC data at body offset 0x{abc_data_offset:X}, length={abc_length}")
            abc_found = (abc_data_offset, abc_length)

        offset += tag_length
        if tag_type == 0:
            break

    if not abc_found:
        print("No DoABC tag found!")
        return

    abc_offset, abc_length = abc_found
    abc_data = body[abc_offset:abc_offset + abc_length]

    # Parse ABC constant pool to find "DerpyMcLongName" string index
    pos = 0
    minor = struct.unpack_from('<H', abc_data, pos)[0]; pos += 2
    major = struct.unpack_from('<H', abc_data, pos)[0]; pos += 2
    print(f"ABC version: {major}.{minor}")

    # Int pool
    int_count, pos = read_u30(abc_data, pos)
    for i in range(1, int_count):
        _, pos = read_u30(abc_data, pos)  # S32 encoded as U30

    # UInt pool
    uint_count, pos = read_u30(abc_data, pos)
    for i in range(1, uint_count):
        _, pos = read_u30(abc_data, pos)

    # Double pool
    double_count, pos = read_u30(abc_data, pos)
    pos += (double_count - 1) * 8  # Each double is 8 bytes

    # String pool - this is what we need
    string_count, pos = read_u30(abc_data, pos)
    print(f"String pool: {string_count} entries")

    target_str = "DerpyMcLongName"
    target_index = None

    for i in range(1, string_count):
        str_len, pos = read_u30(abc_data, pos)
        s = abc_data[pos:pos + str_len].decode('utf-8', errors='replace')
        if s == target_str:
            target_index = i
            print(f"Found '{target_str}' at string index {i}")
        pos += str_len

    if target_index is None:
        print(f"String '{target_str}' not found in constant pool!")
        return

    # Now search for pushstring <target_index> in method bodies
    # pushstring = opcode 0x2C, followed by U30 string index
    target_u30 = encode_u30(target_index)
    pushstring_pattern = bytes([0x2C]) + target_u30
    print(f"Searching for pushstring pattern: {pushstring_pattern.hex()} (0x2C + U30({target_index}))")

    # Search in the entire ABC data for this pattern
    search_pos = 0
    matches = []
    while True:
        found = abc_data.find(pushstring_pattern, search_pos)
        if found == -1:
            break
        matches.append(found)
        search_pos = found + 1

    print(f"Found {len(matches)} pushstring matches in ABC data")

    for match in matches:
        abc_match_offset = match
        body_match_offset = abc_offset + match

        print(f"\npushstring 'DerpyMcLongName' at ABC offset 0x{abc_match_offset:X} (body offset 0x{body_match_offset:X})")

        # Search backwards for iffalse (0x12) - should be within ~50 bytes before
        # We need to search for 0x12 followed by a S24 offset
        # The iffalse should jump past the dummy game block

        # Look back up to 100 bytes for 0x12
        for back in range(1, 100):
            check_pos = match - back
            if check_pos < 0:
                break
            if abc_data[check_pos] == 0x12:
                # This might be iffalse - read the S24 offset
                if check_pos + 3 < len(abc_data):
                    s24 = abc_data[check_pos + 1] | (abc_data[check_pos + 2] << 8) | (abc_data[check_pos + 3] << 16)
                    if s24 & 0x800000:
                        s24 -= 0x1000000

                    body_iffalse_offset = abc_offset + check_pos
                    # The actual offset in the decompressed SWF (body) for the patch
                    # Add 8 for the SWF header that was stripped
                    decompressed_offset = body_iffalse_offset

                    print(f"  Candidate iffalse at ABC offset 0x{check_pos:X} (body offset 0x{body_iffalse_offset:X})")
                    print(f"  S24 jump offset: {s24} (0x{s24 & 0xFFFFFF:06X})")
                    print(f"  Byte at position: 0x{abc_data[check_pos]:02X}")
                    print(f"  Next 4 bytes: {abc_data[check_pos:check_pos+4].hex()}")

                    # Verify: also check for getproperty developerVersion pattern before iffalse
                    # getproperty = 0x66
                    for back2 in range(1, 20):
                        if check_pos - back2 >= 0 and abc_data[check_pos - back2] == 0x66:
                            print(f"  getproperty (0x66) found {back2} bytes before iffalse")
                            break

                    # Check for getlex (0x60) before getproperty
                    for back3 in range(1, 30):
                        if check_pos - back2 - back3 >= 0 and abc_data[check_pos - back2 - back3] == 0x60:
                            print(f"  getlex (0x60) found {back2 + back3} bytes before iffalse")
                            break

if __name__ == '__main__':
    main()
