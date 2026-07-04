"""
Tests for KERN-LITE protocol cross validation.

file: tests/gs/test_cross_vectors.py
author: Smallejoo
date: 2026-04-07
"""
from groundstation.frame import Decoder, FrameType


ACK_VECTOR = bytes([
    0xAB, 0x20, 0x00, 0x00,
    0xF2, 0x9F, 0x0C, 0xC7,
    0xCD,
])

STATUS14_VECTOR = bytes([
    0xAB, 0x12, 0x0E, 0x00,
    0x00, 0x01, 0x04, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00,
    0x56, 0xEC, 0x90, 0xF4,
    0xCD,
])

RECORD32_VECTOR = bytes([
    0xAB, 0x10, 0x20, 0x00,
    0x00, 0x01, 0x02, 0x03,
    0x04, 0x05, 0x06, 0x07,
    0x08, 0x09, 0x0A, 0x0B,
    0x0C, 0x0D, 0x0E, 0x0F,
    0x10, 0x11, 0x12, 0x13,
    0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1A, 0x1B,
    0x1C, 0x1D, 0x1E, 0x1F,
    0x1D, 0x0B, 0x42, 0x85,
    0xCD,
])


def decode_all(data: bytes):
    dec = Decoder()

    for b in data:
        frame = dec.feed(b)

        if frame is not None:
            return frame

    return None


def check_vector(name: str, data: bytes, expected_type: FrameType, expected_len: int):
    frame = decode_all(data)

    assert frame is not None
    assert frame.type == expected_type
    assert len(frame.payload) == expected_len

    print(f"[OK] {name} decoded")


def test_ack_vector_decodes():
    check_vector("ACK_VECTOR", ACK_VECTOR, FrameType.Ack, 0)


def test_status14_vector_decodes():
    check_vector("STATUS14_VECTOR", STATUS14_VECTOR, FrameType.Status, 14)


def test_record32_vector_decodes():
    check_vector("RECORD32_VECTOR", RECORD32_VECTOR, FrameType.Record, 32)


def main():
    check_vector("ACK_VECTOR", ACK_VECTOR, FrameType.Ack, 0)
    check_vector("STATUS14_VECTOR", STATUS14_VECTOR, FrameType.Status, 14)
    check_vector("RECORD32_VECTOR", RECORD32_VECTOR, FrameType.Record, 32)

    print("ALL PYTHON CROSS VECTOR TESTS PASSED")


if __name__ == "__main__":
    main()
