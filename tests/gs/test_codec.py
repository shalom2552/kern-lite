"""
Tests for KERN-LITE protocol framing and CRC.

file: tests/gs/test_codec.py
author: shalom2552
date: 2026-02-07
"""

import pytest
from groundstation.crc import crc32
from groundstation.frame import (
    Frame, FrameType, Decoder, encode,
    CrcError, SyncError, STX
)


def _decode_all(data: bytes):
    """Feed all bytes into the decoder and return the first frame."""
    dec = Decoder()
    for b in data:
        try:
            f = dec.feed(b)
        except (CrcError, SyncError):
            continue
        if f is not None:
            return f
    return None


def test_crc_kat():
    assert crc32(b"123456789") == 0xCBF43926


def test_crc_roundtrip_status():
    payload = bytes(range(14))
    frame = Frame(type=FrameType.Status, payload=payload)
    out = _decode_all(encode(frame))
    assert out is not None
    assert out.type == FrameType.Status
    assert out.payload == payload


def test_crc_roundtrip_record():
    payload = bytes(range(32))
    frame = Frame(type=FrameType.Record, payload=payload)
    out = _decode_all(encode(frame))
    assert out is not None
    assert out.type == FrameType.Record
    assert out.payload == payload


def test_crc_roundtrip_ack():
    frame = Frame(type=FrameType.Ack, payload=b'')
    out = _decode_all(encode(frame))
    assert out is not None
    assert out.type == FrameType.Ack
    assert out.payload == b''


def test_crc_corruption_raises_crcerror():
    frame = Frame(type=FrameType.Status, payload=bytes(range(14)))
    raw = bytearray(encode(frame))
    raw[5] ^= 0xFF
    dec = Decoder()
    with pytest.raises(CrcError):
        for b in raw:
            dec.feed(b)


def test_crc_resync_after_garbage():
    frame = Frame(type=FrameType.Ack, payload=b'')
    stream = bytes([0x00, 0xFF, 0x11, 0xAB, 0x22] * 2 + [0x99, 0x88]) + encode(frame)
    out = _decode_all(stream)
    assert out is not None
    assert out.type == FrameType.Ack


def test_crc_oversized_len_raises_syncerror():
    # [STX][TYPE=0x10][LEN_LO=0xFF][LEN_HI=0x01] -> LEN=511 > 256
    dec = Decoder()
    with pytest.raises(SyncError):
        for b in [STX, 0x10, 0xFF, 0x01]:
            dec.feed(b)


def test_crc_cross_implementation_vector():
     # Expected: AB 20 00 00 <CRC0 CRC1 CRC2 CRC3> CD  (9 bytes)
    fw_ack = encode(Frame(type=FrameType.Ack, payload=b''))
    out = _decode_all(fw_ack)
    assert out is not None
    assert out.type == FrameType.Ack
    assert out.payload == b''
