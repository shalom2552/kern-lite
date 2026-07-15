"""
Analytics tests for groundstation.link_quality.LinkQualityMonitor.

file: tests/gs/test_link_quality.py
author: Smallejoo
date: 2026-14-07
"""
from __future__ import annotations
import pytest

from groundstation.link_quality import LinkQualityMonitor


class EventSink:
    def __init__(self) -> None:
        self.events = []

    def add(self, category, wall_time=None, session_seq=None, message="") -> None:
        self.events.append(
            {
                "category": str(category),
                "wall_time": wall_time,
                "session_seq": session_seq,
                "message": message,
            }
        )


def test_zero_errors_and_zero_jitter_gives_full_quality():
    monitor = LinkQualityMonitor()
    monitor.update(0.0)  # establish the evaluation baseline

    t = 0.0
    for _ in range(10):
        t += 0.1
        monitor.on_frame(t)

    monitor.update(5.0)  # >= interval_s triggers evaluation

    assert monitor.quality_pct == pytest.approx(100.0)
    assert not monitor.degraded
    assert not monitor.poor


def test_weighted_errors_reduce_quality_below_80_percent():
    monitor = LinkQualityMonitor()
    monitor.update(0.0)

    t = 0.0
    for _ in range(17):
        t += 0.1
        monitor.on_frame(t)
    monitor.on_crc_error()
    monitor.on_crc_error()
    monitor.on_sync_error()
    monitor.on_seq_gap(1)

    monitor.update(5.0)

    assert monitor.quality_pct < 80.0


def test_total_records_drop_fires_reboot_event():
    sink = EventSink()
    monitor = LinkQualityMonitor(alert_log=sink)

    rebooted_first = monitor.on_status(total_records=1000, wall_time=10.0, seq=1000)
    rebooted_second = monitor.on_status(total_records=3, wall_time=11.0, seq=3)

    assert rebooted_first is False
    assert rebooted_second is True
    assert any("REBOOT" in event["category"].upper() for event in sink.events)



def test_crc_errors_without_any_good_frames_does_not_crash():
    monitor = LinkQualityMonitor()
    monitor.update(0.0)

    monitor.on_crc_error()
    monitor.on_sync_error()

    monitor.update(5.0)

    assert 0.0 <= monitor.quality_pct <= 100.0
