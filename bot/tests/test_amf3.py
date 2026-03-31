"""Smoke test for AMF3 codec -- roundtrip encode/decode."""

from bot.amf3 import encode_amf3_value, decode_amf3


def test_roundtrip_string():
    data = encode_amf3_value("hello")
    result = decode_amf3(data)
    assert result == "hello"


def test_roundtrip_integer():
    data = encode_amf3_value(42)
    result = decode_amf3(data)
    assert result == 42


def test_roundtrip_float():
    data = encode_amf3_value(3.14)
    result = decode_amf3(data)
    assert abs(result - 3.14) < 0.001


def test_roundtrip_boolean():
    for val in [True, False]:
        data = encode_amf3_value(val)
        result = decode_amf3(data)
        assert result == val


def test_roundtrip_none():
    data = encode_amf3_value(None)
    result = decode_amf3(data)
    assert result is None


def test_roundtrip_list():
    msg = ["Msg", 42, ["Click", {"_type": "card clicked", "_id": 0}]]
    data = encode_amf3_value(msg)
    result = decode_amf3(data)
    assert result[0] == "Msg"
    assert result[1] == 42
    assert result[2][0] == "Click"
    assert result[2][1]["_type"] == "card clicked"


def test_roundtrip_nested_dict():
    obj = {"name": "Drone", "buyCost": "3H", "supply": 20}
    data = encode_amf3_value(obj)
    result = decode_amf3(data)
    assert result["name"] == "Drone"
    assert result["supply"] == 20


def test_roundtrip_empty_list():
    data = encode_amf3_value([])
    result = decode_amf3(data)
    assert result == []


def test_roundtrip_empty_dict():
    data = encode_amf3_value({})
    result = decode_amf3(data)
    assert result == {}


def test_roundtrip_large_integer():
    """AMF3 U29 supports up to 2^28-1 = 268435455."""
    data = encode_amf3_value(268435455)
    result = decode_amf3(data)
    assert result == 268435455


def test_roundtrip_negative_integer():
    """Negative integers should be encoded as doubles in AMF3."""
    data = encode_amf3_value(-1)
    result = decode_amf3(data)
    assert result == -1
