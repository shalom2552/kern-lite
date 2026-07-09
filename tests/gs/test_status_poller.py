"""
Tests for StatusPoller: reboot detection, malformed STATUS handling, stop().

file: tests/gs/test_status_poller.py
author: shalom2552
date: 2026-07-10
"""
import logging
import struct

from groundstation.commands import CommandSender, StatusPoller
from groundstation.frame import Frame, FrameType
from groundstation.state import DeviceStateModel
from groundstation.storage_panel import StorageModel


class FakeLink:
    """Minimal link stub: records outgoing frames, always connected."""

    def __init__(self):
        self.connection_state = "connected"
        self.sent = []
        self.recorded = []

    def record_command(self, frame_type):
        self.recorded.append(frame_type)

    def send_frame(self, frame):
        self.sent.append(frame)


def make_status_frame(state=0, sd_mounted=1, file_count=4, current_file=0,
                      total_records=0, wrap_count=0, records_in_file=0):
    payload = struct.pack(
        "<BBBBIIH",
        state, sd_mounted, file_count, current_file,
        total_records, wrap_count, records_in_file,
    )
    return Frame(FrameType.Status, payload)


def make_poller():
    link = FakeLink()
    poller = StatusPoller(link, CommandSender(), DeviceStateModel(), StorageModel())
    return link, poller


def test_status_growth_no_reboot_warning(caplog):
    link, poller = make_poller()
    with caplog.at_level(logging.WARNING):
        poller.handle_status_reply(make_status_frame(total_records=100))
        poller.handle_status_reply(make_status_frame(total_records=200))

    assert "REBOOT_DETECTED" not in caplog.text
    assert link.sent == []
    assert poller.storage_model.total_records == 200


def test_large_drop_flags_reboot_and_reissues_status(caplog):
    link, poller = make_poller()
    poller.handle_status_reply(make_status_frame(total_records=5000))
    with caplog.at_level(logging.WARNING):
        poller.handle_status_reply(make_status_frame(total_records=3))

    assert "REBOOT_DETECTED" in caplog.text
    assert link.recorded == [FrameType.CmdStatus]
    assert len(link.sent) == 1
    assert link.sent[0].type == FrameType.CmdStatus


def test_reissue_skipped_when_disconnected(caplog):
    link, poller = make_poller()
    poller.handle_status_reply(make_status_frame(total_records=5000))
    link.connection_state = "disconnected"
    with caplog.at_level(logging.WARNING):
        poller.handle_status_reply(make_status_frame(total_records=3))

    assert "REBOOT_DETECTED" in caplog.text
    assert link.sent == []


def test_malformed_status_dropped_without_crash(caplog):
    link, poller = make_poller()
    poller.handle_status_reply(make_status_frame(total_records=100))
    with caplog.at_level(logging.ERROR):
        poller.handle_status_reply(Frame(FrameType.Status, b"\x00\x01\x02"))

    assert "malformed STATUS" in caplog.text
    assert poller.storage_model.total_records == 100  # unchanged


def test_stop_ends_thread_promptly():
    link, poller = make_poller()
    poller.poll_interval_s = 60.0  # would block a plain sleep-based loop
    poller.start()
    poller.stop()
    poller.join(timeout=1.0)

    assert not poller.is_alive()
