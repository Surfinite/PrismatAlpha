"""
AMF3 binary codec — encode/decode Python objects to/from AMF3 bytes.

Extracted from <ladder>'s prismata_amf3.py (the battle-tested
spectator-bot codec). Only the pure codec is included here — no sniffer,
proxy, session, or game-logic code.

AMF3 spec: https://wwwimages2.adobe.com/content/dam/acom/en/devnet/pdf/amf-file-format-spec.pdf
"""

import struct


# ============================================================
# AMF3 Decoder
# ============================================================

class AMF3Decoder:
    """Decodes AMF3 binary data into Python objects."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.string_refs: list[str] = []
        self.object_refs: list = []
        self.trait_refs: list[dict] = []

    def read_u8(self) -> int:
        val = self.data[self.pos]
        self.pos += 1
        return val

    def read_u29(self) -> int:
        result = 0
        for i in range(4):
            b = self.read_u8()
            if i < 3:
                result = (result << 7) | (b & 0x7F)
                if not (b & 0x80):
                    return result
            else:
                result = (result << 8) | b
                return result
        return result

    def read_string(self) -> str:
        ref = self.read_u29()
        if ref & 1:  # inline
            length = ref >> 1
            if length == 0:
                return ""
            s = self.data[self.pos:self.pos + length].decode('utf-8', errors='replace')
            self.pos += length
            self.string_refs.append(s)
            return s
        else:  # reference
            idx = ref >> 1
            if idx < len(self.string_refs):
                return self.string_refs[idx]
            return f"<string_ref:{idx}>"

    def read_value(self):
        marker = self.read_u8()

        if marker == 0x00:  # undefined
            return None
        elif marker == 0x01:  # null
            return None
        elif marker == 0x02:  # false
            return False
        elif marker == 0x03:  # true
            return True
        elif marker == 0x04:  # integer
            val = self.read_u29()
            if val >= 0x10000000:
                val -= 0x20000000
            return val
        elif marker == 0x05:  # double
            val = struct.unpack_from('>d', self.data, self.pos)[0]
            self.pos += 8
            return val
        elif marker == 0x06:  # string
            return self.read_string()
        elif marker == 0x07:  # XMLDocument
            return self._read_string_data()
        elif marker == 0x08:  # date
            ref = self.read_u29()
            if ref & 1:
                ms = struct.unpack_from('>d', self.data, self.pos)[0]
                self.pos += 8
                self.object_refs.append(ms)
                return {"__date__": ms}
            return self.object_refs[ref >> 1]
        elif marker == 0x09:  # array
            return self._read_array()
        elif marker == 0x0A:  # object
            return self._read_object()
        elif marker == 0x0B:  # XML
            return self._read_string_data()
        elif marker == 0x0C:  # ByteArray
            ref = self.read_u29()
            if ref & 1:
                length = ref >> 1
                ba = self.data[self.pos:self.pos + length]
                self.pos += length
                self.object_refs.append(ba)
                return {"__bytes__": ba.hex()[:40] + ("..." if length > 20 else "")}
            return self.object_refs[ref >> 1]
        else:
            return f"<unknown:0x{marker:02x}>"

    def _read_string_data(self) -> str:
        ref = self.read_u29()
        if ref & 1:
            length = ref >> 1
            s = self.data[self.pos:self.pos + length].decode('utf-8', errors='replace')
            self.pos += length
            self.object_refs.append(s)
            return s
        return self.object_refs[ref >> 1]

    def _read_array(self):
        ref = self.read_u29()
        if ref & 1:
            count = ref >> 1
            arr = []
            self.object_refs.append(arr)
            # Associative portion
            assoc = {}
            while True:
                key = self.read_string()
                if key == "":
                    break
                assoc[key] = self.read_value()
            # Dense portion
            for _ in range(count):
                arr.append(self.read_value())
            if assoc:
                return {"__assoc__": assoc, "__dense__": arr}
            return arr
        else:
            idx = ref >> 1
            if idx < len(self.object_refs):
                return self.object_refs[idx]
            return f"<array_ref:{idx}>"

    def _read_object(self):
        ref = self.read_u29()
        if ref & 1:
            # Inline object
            traits_ref = ref >> 1
            if traits_ref & 1:
                # Inline traits
                traits_info = traits_ref >> 1
                is_externalizable = bool(traits_info & 1)
                is_dynamic = bool(traits_info & 2)
                sealed_count = traits_info >> 2
                class_name = self.read_string()
                trait = {
                    "class": class_name,
                    "externalizable": is_externalizable,
                    "dynamic": is_dynamic,
                    "sealed_members": [],
                }
                for _ in range(sealed_count):
                    trait["sealed_members"].append(self.read_string())
                self.trait_refs.append(trait)
            else:
                # Trait reference
                trait_idx = traits_ref >> 1
                if trait_idx < len(self.trait_refs):
                    trait = self.trait_refs[trait_idx]
                else:
                    trait = {
                        "class": "?",
                        "sealed_members": [],
                        "dynamic": False,
                        "externalizable": False,
                    }

            obj = {}
            if trait.get("class"):
                obj["__class__"] = trait["class"]
            self.object_refs.append(obj)

            if trait.get("externalizable"):
                obj["__externalizable__"] = True
                return obj

            for member in trait.get("sealed_members", []):
                obj[member] = self.read_value()

            if trait.get("dynamic"):
                while True:
                    key = self.read_string()
                    if key == "":
                        break
                    obj[key] = self.read_value()

            return obj
        else:
            idx = ref >> 1
            if idx < len(self.object_refs):
                return self.object_refs[idx]
            return f"<object_ref:{idx}>"


# ============================================================
# AMF3 Encoder
# ============================================================

def encode_u29(val: int) -> bytes:
    """Encode a U29 variable-length integer (29-bit unsigned)."""
    val = val & 0x1FFFFFFF  # Ensure 29-bit
    if val < 0x80:
        return bytes([val])
    elif val < 0x4000:
        return bytes([(val >> 7) | 0x80, val & 0x7F])
    elif val < 0x200000:
        return bytes([(val >> 14) | 0x80, ((val >> 7) & 0x7F) | 0x80, val & 0x7F])
    else:
        return bytes([
            ((val >> 22) & 0x7F) | 0x80,
            ((val >> 15) & 0x7F) | 0x80,
            ((val >> 8) & 0x7F) | 0x80,
            val & 0xFF,
        ])


def encode_amf3_string(val: str) -> bytes:
    """Encode a string as AMF3 inline string (no reference table)."""
    encoded = val.encode('utf-8')
    return encode_u29((len(encoded) << 1) | 1) + encoded


def encode_amf3_value(val) -> bytes:
    """Encode a Python value as AMF3 bytes.

    Supports: None, bool, int, float, str, list, dict.
    """
    # Check bool before int (bool is a subclass of int in Python)
    if isinstance(val, bool):
        return b'\x03' if val else b'\x02'
    elif isinstance(val, str):
        return b'\x06' + encode_amf3_string(val)
    elif isinstance(val, int):
        # AMF3 integer: 29-bit signed, range -268435456 to 268435455
        if -0x10000000 <= val < 0x10000000:
            return b'\x04' + encode_u29(val)
        else:
            return b'\x05' + struct.pack('>d', float(val))
    elif isinstance(val, float):
        return b'\x05' + struct.pack('>d', val)
    elif isinstance(val, list):
        result = b'\x09' + encode_u29((len(val) << 1) | 1)
        result += b'\x01'  # empty associative portion
        for item in val:
            result += encode_amf3_value(item)
        return result
    elif isinstance(val, dict):
        # Encode as anonymous dynamic AMF3 object.
        # Traits header: inline object + inline traits + dynamic + 0 sealed members
        # ref bit=1, traits inline bit=1, dynamic bit=1, externalizable=0, sealed_count=0
        # Combined: 0x0B (traits_ref=0b...1011 → ref=1, traits_inline=1, dynamic=1, ext=0, sealed=0)
        result = b'\x0A'  # object marker
        result += encode_u29(0x0B)  # inline object, inline traits, dynamic, 0 sealed
        result += b'\x01'  # empty class name
        for k, v in val.items():
            result += encode_amf3_string(str(k))
            result += encode_amf3_value(v)
        result += b'\x01'  # empty string terminates dynamic members
        return result
    elif val is None:
        return b'\x01'  # null
    return b'\x00'  # undefined


# ============================================================
# Public API
# ============================================================

def decode_amf3(data: bytes):
    """Decode a single AMF3 value from *data* and return it as a Python object."""
    decoder = AMF3Decoder(data)
    return decoder.read_value()
