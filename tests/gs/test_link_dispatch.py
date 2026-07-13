"""
Integrity checking for decoded telemetry records.

file: tests/gs/test_link_dispatch.py
author: Yair
date: 2026-12-07
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from groundstation.crc import crc32
from groundstation.frame import Frame, FrameType, encode, Decoder
from groundstation.link import SerialLink
from groundstation.state import DeviceStateModel, STATE_RECORDING
from groundstation.storage_panel import StorageModel
from groundstation.integrity import IntegrityChecker

_HEAD_FMT = "<IHHhhHHHBBB7x"


def _record_payload(seq=1):
    head = struct.pack(_HEAD_FMT, 100, 0, seq, 253, 220, 450, 32768, 16384, 0, 1, 0)
    return head + struct.pack("<I", crc32(head))


def _status_payload(state=1, sd_mounted=1, file_count=4, current_file=0,
                     total_records=10, wrap_count=0, records_in_file=10):
    return struct.pack("<BBBBIIH", state, sd_mounted, file_count, current_file,
                        total_records, wrap_count, records_in_file)


class _FakeSerial:
    """Feeds pre-encoded bytes to receive_frame() without a real port."""
    def __init__(self, data: bytes):
        self._buf = data
        self.is_open = True

    @property
    def in_waiting(self):
        return len(self._buf)

    def read(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk


def _make_link():
    link = SerialLink(
        state_model=DeviceStateModel(),
        storage_model=StorageModel(),
        telemetry_model=None,  # not needed for this test
        integrity_checker=IntegrityChecker(),
    )
    return link


def test_status_frame_updates_state_and_storage_models():
    link = _make_link()
    payload = _status_payload(state=STATE_RECORDING, total_records=42)
    frame_bytes = encode(Frame(type=FrameType.Status, payload=payload))
    link.ser = _FakeSerial(frame_bytes)

    result = link.receive_frame()

    assert result is not None
    assert link.state_model.state == STATE_RECORDING
    assert link.storage_model.total_records == 42
    assert link.rx_count == 1


def test_record_frame_updates_integrity_and_storage_counters(caplog):
    link = _make_link()
    payload = _record_payload(seq=7)
    frame_bytes = encode(Frame(type=FrameType.Record, payload=payload))
    link.ser = _FakeSerial(frame_bytes)

    with caplog.at_level("WARNING"):
        result = link.receive_frame()

    assert result is not None
    assert link.storage_model.live_record_count == 1
    assert link.storage_model.replay_record_count == 0
    assert "STORAGE_CORRUPTION_WARNING" not in caplog.text  # valid record, no warnings


def test_record_during_replay_counts_as_replay():
    link = _make_link()
    link.record_command(FrameType.CmdReplay)  # sets _in_replay = True
    payload = _record_payload(seq=1)
    frame_bytes = encode(Frame(type=FrameType.Record, payload=payload))
    link.ser = _FakeSerial(frame_bytes)

    link.receive_frame()

    assert link.storage_model.replay_record_count == 1
    assert link.storage_model.live_record_count == 0


def test_corrupted_frame_counts_crc_error_and_is_dropped():
    link = _make_link()
    data = bytearray(encode(Frame(type=FrameType.Status, payload=_status_payload())))
    data[6] ^= 0xFF  # flip a payload byte so the frame CRC no longer matches
    link.ser = _FakeSerial(bytes(data))

    frame = link.receive_frame()

    assert frame is None
    assert link.crc_error_count == 1


def test_back_to_back_frames_in_one_chunk_all_returned():
    # STATUS followed immediately by ACK, as the firmware replies to CMD_START.
    link = _make_link()
    data = encode(Frame(type=FrameType.Status, payload=_status_payload()))
    data += encode(Frame(type=FrameType.Ack, payload=b""))
    link.ser = _FakeSerial(data)

    first = link.receive_frame()
    second = link.receive_frame()

    assert first is not None and first.type == FrameType.Status
    assert second is not None and second.type == FrameType.Ack


def test_replay_burst_frames_not_dropped():
    # 60 RECORD frames and the closing ACK arriving as one burst.
    link = _make_link()
    link.record_command(FrameType.CmdReplay)
    data = b"".join(
        encode(Frame(type=FrameType.Record, payload=_record_payload(seq=i)))
        for i in range(1, 61)
    )
    data += encode(Frame(type=FrameType.Ack, payload=b""))
    link.ser = _FakeSerial(data)

    frames = []
    frame = link.receive_frame()
    while frame is not None:
        frames.append(frame)
        frame = link.receive_frame()

    assert len(frames) == 61
    assert frames[-1].type == FrameType.Ack
    assert link.storage_model.replay_record_count == 60


def test_ack_ends_replay_transaction():
    link = _make_link()
    link.record_command(FrameType.CmdReplay)
    assert link._in_replay is True

    frame_bytes = encode(Frame(type=FrameType.Ack, payload=b""))
    link.ser = _FakeSerial(frame_bytes)
    link.receive_frame()

    assert link._in_replay is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
