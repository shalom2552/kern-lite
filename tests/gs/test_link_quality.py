"""
Analytics tests for groundstation.link_quality.LinkQualityMonitor.

file: tests/gs/test_link_quality.py
"""
from __future__ import annotations

import inspect

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


def _call_if_present(obj, names: tuple[str, ...], *args, **kwargs) -> bool:
    for name in names:
        method = getattr(obj, name, None)
        if method is None:
            continue
        signature = inspect.signature(method)
        filtered = {key: value for key, value in kwargs.items() if key in signature.parameters}
        method(*args, **filtered)
        return True
    return False


def _set_counters(monitor: LinkQualityMonitor, **values) -> None:
    for name, value in values.items():
        if hasattr(monitor, name):
            setattr(monitor, name, value)


def _compute_quality(monitor: LinkQualityMonitor) -> float:
    for name in ("compute", "compute_quality", "update_quality", "tick"):
        method = getattr(monitor, name, None)
        if method is not None:
            result = method()
            if result is not None:
                return float(result)
            break
    return float(monitor.quality_pct)


def test_zero_errors_and_zero_jitter_gives_full_quality():
    monitor = LinkQualityMonitor()
    _set_counters(
        monitor,
        crc_error_rate=0.0,
        sync_error_rate=0.0,
        sequence_gap_rate=0.0,
        gap_rate=0.0,
        nack_rate=0.0,
        jitter_s=0.0,
        frame_timing_jitter=0.0,
    )

    assert _compute_quality(monitor) == pytest.approx(100.0)
    assert monitor.quality_pct == pytest.approx(100.0)
    assert not monitor.degraded
    assert not monitor.poor


def test_weighted_errors_reduce_quality_below_80_percent():
    monitor = LinkQualityMonitor()
    _set_counters(
        monitor,
        crc_error_rate=0.10,
        sync_error_rate=0.05,
        sequence_gap_rate=0.05,
        gap_rate=0.05,
        nack_rate=0.0,
        jitter_s=0.0,
        frame_timing_jitter=0.0,
    )

    assert _compute_quality(monitor) < 80.0


def test_total_records_drop_fires_reboot_event():
    sink = EventSink()
    try:
        monitor = LinkQualityMonitor(alert_log=sink)
    except TypeError:
        monitor = LinkQualityMonitor()
        monitor.alert_log = sink

    first_seen = _call_if_present(
        monitor,
        ("on_status", "status_seen", "update_status"),
        total_records=1000,
        seq=1000,
        wall_time=10.0,
    )
    second_seen = _call_if_present(
        monitor,
        ("on_status", "status_seen", "update_status"),
        total_records=3,
        seq=3,
        wall_time=11.0,
    )

    assert first_seen and second_seen
    assert any("REBOOT" in event["category"].upper() for event in sink.events)
