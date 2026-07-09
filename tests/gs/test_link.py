"""
test file that uses hardcoded captured UART

file: tests/gs/test_link.py
author: Smallejoo
date: 2026-06-07
"""
from groundstation.frame import Decoder  


STATUS_HEX = "AB 12 0E 00 00 01 04 00 00 00 00 00 00 00 00 00 00 00 56 EC 90 F4 CD"
NACK_BAD_COMMAND_HEX = "AB 21 01 00 02 5C 1C 06 D6 CD"

STATUS_TYPE = 0x12
NACK_TYPE = 0x21
BAD_COMMAND = 0x02


def decode_hex_stream(hex_string: str):
    decoder = Decoder()
    data = bytes.fromhex(hex_string)

    for byte in data:
        result = decoder.feed(byte)

        if result is not None:  
            return result

    return None

def test_status_vector_decodes():
    frame = decode_hex_stream(STATUS_HEX)

    assert frame is not None
    assert frame.type == STATUS_TYPE
    assert len(frame.payload) == 14

    assert frame.payload[0] == 0
    assert frame.payload[1] == 1
    assert frame.payload[2] == 4
    assert frame.payload[3] == 0

    assert int.from_bytes(frame.payload[4:8], "little") == 0
    assert int.from_bytes(frame.payload[8:12], "little") == 0
    assert int.from_bytes(frame.payload[12:14], "little") == 0


def test_nack_bad_command_decodes():
    frame = decode_hex_stream(NACK_BAD_COMMAND_HEX)

    assert frame is not None
    assert frame.type == NACK_TYPE
    assert len(frame.payload) == 1
    assert frame.payload[0] == BAD_COMMAND
