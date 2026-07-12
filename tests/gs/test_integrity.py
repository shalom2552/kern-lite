"""
Integrity checking for decoded telemetry records.

file: tests/gs/test_integrity.py
author: Yair
date: 2026-12-07
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from groundstation.crc import crc32
from groundstation.frame import Frame, FrameType
from groundstation.integrity import IntegrityChecker
from groundstation.telemetry import RecordDecoder

_HEAD_FMT = "<IHHhhHHHBBB7x"


def _build_record_payload(seq=1, crc_override=None):
    head = struct.pack(_HEAD_FMT, 100, 0, seq, 250, 220, 450, 32768, 16384, 0, 1, 0)
    crc = crc_override if crc_override is not None else crc32(head)
    return head + struct.pack("<I", crc)


def test_valid_record_no_warning(caplog):
    checker = IntegrityChecker()
    payload = _build_record_payload(seq=1)
    frame = Frame(type=FrameType.Record, payload=payload)

    with caplog.at_level("WARNING"):
        ok = checker.check_frame(frame)

    assert ok is True
    assert "STORAGE_CORRUPTION_WARNING" not in caplog.text


def test_corrupted_payload_flags_storage_corruption(caplog):
    checker = IntegrityChecker()
    payload = bytearray(_build_record_payload(seq=1))
    payload[10] ^= 0xFF  # corrupt dht_temp_c, leave stored CRC stale
    frame = Frame(type=FrameType.Record, payload=bytes(payload))

    with caplog.at_level("WARNING"):
        ok = checker.check_frame(frame)

    assert ok is False
    assert "STORAGE_CORRUPTION_WARNING" in caplog.text


def test_first_record_of_session_is_not_a_gap():
    # last_seq=None means "nothing seen yet this session" -- must not crash
    # and must not be reported as a gap.
    checker = IntegrityChecker()
    payload = _build_record_payload(seq=42)
    record = RecordDecoder.decode(payload)

    gap = checker.check_sequence(record, None)

    assert gap == 0


def test_sequence_gap_detected_at_correct_record(caplog):
    checker = IntegrityChecker()
    last_seq = None
    gaps = []
    with caplog.at_level("WARNING"):
        for seq in (1, 2, 3, 7):
            payload = _build_record_payload(seq=seq)
            record = RecordDecoder.decode(payload)
            gap = checker.check_sequence(record, last_seq)
            gaps.append(gap)
            last_seq = seq

    assert gaps == [0, 0, 0, 3]
    assert "SEQ_GAP size=3" in caplog.text


def test_non_record_frame_always_ok(caplog):
    checker = IntegrityChecker()
    frame = Frame(type=FrameType.Ack, payload=b"")

    with caplog.at_level("WARNING"):
        ok = checker.check_frame(frame)

    assert ok is True
    assert caplog.text == ""


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
