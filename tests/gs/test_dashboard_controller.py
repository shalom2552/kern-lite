"""
Headless tests for dashboard.controller.DashboardController: event fan-out
(sequence gaps, state transitions, channel alerts, reboots), TX/RX raw frame
logging, and idempotent shutdown. No tkinter involved.

file: tests/gs/test_dashboard_controller.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.controller import DashboardController
from groundstation.crc import crc32
from groundstation.frame import Frame, FrameType, encode

_HEAD_FMT = "<IHHhhHHHBBB7x"


def _record_payload(seq=1, alert_bits=0, state=1):
    head = struct.pack(_HEAD_FMT, 100, 0, seq, 253, 220, 450, 32768, 16384,
                       alert_bits, state, 0)
    return head + struct.pack("<I", crc32(head))


def _status_payload(state=1, sd_mounted=1, total_records=10):
    return struct.pack("<BBBBIIH", state, sd_mounted, 4, 0, total_records, 0,
                       total_records % 256)


def _frames_bytes(*frames: Frame) -> bytes:
    return b"".join(encode(f) for f in frames)


class _FakeSerial:
    """Feeds pre-encoded bytes to receive_frame() and captures writes."""

    def __init__(self, data: bytes = b""):
        self._buf = data
        self.is_open = True
        self.written: list[bytes] = []

    @property
    def in_waiting(self):
        return len(self._buf)

    def read(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk

    def write(self, data):
        self.written.append(bytes(data))
        return len(data)


def _wired_controller(tmp_path, rx: bytes = b""):
    """Controller with an open session and a fake connected serial port."""
    controller = DashboardController(session_base_dir=str(tmp_path))
    controller.session.on_connect("FAKE")
    controller._session_open = True
    controller.link.ser = _FakeSerial(rx)
    controller.link.connection_state = "connected"
    return controller


def _entries(controller, category):
    return [e for e in controller.alert_log.entries if e.category == category]


def test_sequence_gap_feeds_chart_quality_and_alert_log(tmp_path):
    rx = _frames_bytes(
        Frame(FrameType.Record, _record_payload(seq=1)),
        Frame(FrameType.Record, _record_payload(seq=5)),  # 3 records skipped
    )
    controller = _wired_controller(tmp_path, rx)

    controller.pump(now=100.0)

    assert controller.chart.gap_notches == [(5, 3)]
    gap_entries = _entries(controller, "SEQ_GAP")
    assert len(gap_entries) == 1
    assert gap_entries[0].session_seq == 5
    assert len(controller.session.records) == 2


def test_state_transition_creates_marker_timeline_band_and_log(tmp_path):
    rx = _frames_bytes(Frame(FrameType.Status, _status_payload(state=1)))
    controller = _wired_controller(tmp_path, rx)

    controller.pump(now=100.0)

    assert len(controller.chart.state_markers) == 1
    assert controller.chart.state_markers[0][1] == "Idle->Recording"
    assert controller.timeline.segments[-1]["state"] == 1
    transitions = _entries(controller, "STATE_TRANSITION")
    assert len(transitions) == 1
    assert transitions[0].message == "Idle -> Recording"


def test_reboot_marks_chart_and_timeline_and_reissues_status(tmp_path):
    rx = _frames_bytes(
        Frame(FrameType.Status, _status_payload(total_records=100)),
        Frame(FrameType.Status, _status_payload(total_records=10)),  # fell > 50%
    )
    controller = _wired_controller(tmp_path, rx)

    controller.pump(now=100.0)

    assert controller.quality.reboot_count == 1
    assert len(controller.chart.reboot_markers) == 1
    assert len(controller.timeline.reboots) == 1
    assert len(_entries(controller, "REBOOT")) == 1
    # Re-issued STATUS went out on the wire.
    assert controller.link.ser.written
    assert controller.link.tx_count >= 1


def test_channel_alert_edges_logged_and_tracked_on_timeline(tmp_path):
    lm35_hi = 0x01  # ALERT_MASKS["lm35"] high bit
    controller = _wired_controller(
        tmp_path, _frames_bytes(Frame(FrameType.Record,
                                      _record_payload(seq=1, alert_bits=lm35_hi))))

    controller.pump(now=100.0)
    assert len(_entries(controller, "ALERT_ACTIVE")) == 1

    controller.link.ser._buf = _frames_bytes(
        Frame(FrameType.Record, _record_payload(seq=2, alert_bits=0)))
    controller.pump(now=101.0)

    assert len(_entries(controller, "ALERT_CLEAR")) == 1
    assert len(controller.timeline.alerts) == 2


def test_replay_records_do_not_flag_sequence_gaps(tmp_path):
    rx = _frames_bytes(
        Frame(FrameType.Record, _record_payload(seq=100)),  # live stream
        Frame(FrameType.Record, _record_payload(seq=101)),
    )
    controller = _wired_controller(tmp_path, rx)
    controller.pump(now=100.0)
    assert controller.chart.gap_notches == []

    # Replay of old records (backwards seq), then ACK, then live resumes.
    controller.link.record_command(FrameType.CmdReplay)
    controller.link.ser._buf = _frames_bytes(
        Frame(FrameType.Record, _record_payload(seq=10)),
        Frame(FrameType.Record, _record_payload(seq=11)),
        Frame(FrameType.Ack),
        Frame(FrameType.Record, _record_payload(seq=102)),
    )
    controller.pump(now=101.0)

    assert controller.chart.gap_notches == []
    assert _entries(controller, "SEQ_GAP") == []
    assert controller.storage_model.replay_record_count == 2


def test_tx_and_rx_frames_logged_to_session(tmp_path):
    rx = _frames_bytes(Frame(FrameType.Status, _status_payload()))
    controller = _wired_controller(tmp_path, rx)

    controller.pump(now=100.0)  # drains RX and fires the 5 s status poll (TX)

    frames_log = os.path.join(controller.session.dir, "frames.log")
    controller.session.close()
    controller._session_open = False
    with open(frames_log) as f:
        directions = [line.split()[1] for line in f if line.strip()]
    assert "RX" in directions
    assert "TX" in directions


def test_command_gating_follows_device_state(tmp_path):
    controller = _wired_controller(tmp_path)
    controller.state_model.state = 0  # Idle
    controller.state_model.sd_mounted = True

    assert controller.command_allowed(FrameType.CmdStart)
    assert not controller.command_allowed(FrameType.CmdStop)
    assert controller.command_allowed(FrameType.CmdReplay)
    assert controller.command_allowed(FrameType.CmdErase)

    controller.state_model.state = 1  # Recording
    assert not controller.command_allowed(FrameType.CmdStart)
    assert controller.command_allowed(FrameType.CmdStop)

    controller.link.connection_state = "disconnected"
    assert not controller.command_allowed(FrameType.CmdStatus)


def test_shutdown_is_idempotent_and_writes_exports(tmp_path):
    controller = _wired_controller(tmp_path)
    session_dir = controller.session.dir

    controller.shutdown()
    controller.shutdown()  # second call must be a no-op

    assert os.path.isfile(os.path.join(session_dir, "alerts.log"))
    assert os.path.isfile(os.path.join(session_dir, "timeline.log"))
    assert controller.session._bin is None  # session files closed
