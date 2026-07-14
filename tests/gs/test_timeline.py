"""
Analytics tests for groundstation.timeline.StateTimeline.

file: tests/gs/test_timeline.py
author: Smallejoo
date: 2026-14-07
"""
from __future__ import annotations
from pathlib import Path
from groundstation.timeline import StateTimeline


def test_timeline_export_contains_two_recording_bands_and_reboot(tmp_path: Path):
    timeline = StateTimeline()

    timeline.on_state_change("Idle", "Recording", wall_time=0.0, session_record_count=0)
    timeline.on_state_change("Recording", "Idle", wall_time=30.0, session_record_count=300)
    timeline.on_state_change("Idle", "Recording", wall_time=60.0, session_record_count=300)
    timeline.on_state_change("Recording", "Idle", wall_time=90.0, session_record_count=600)
    timeline.on_reboot(seq=300, wall_time=60.0)

    export_path = tmp_path / "timeline.txt"
    timeline.export_text(export_path)

    text = export_path.read_text(encoding="utf-8")
    recording_lines = [line for line in text.splitlines() if "Recording" in line]

    assert len(recording_lines) == 2
    assert all("30" in line for line in recording_lines)
    assert "300" in text
    assert "REBOOT" in text.upper()
    assert "60" in text


def test_timeline_records_reboot_event_at_expected_position():
    timeline = StateTimeline()

    timeline.on_state_change("Idle", "Recording", wall_time=0.0, session_record_count=0)
    timeline.on_state_change("Recording", "Idle", wall_time=30.0, session_record_count=300)
    timeline.on_state_change("Idle", "Recording", wall_time=60.0, session_record_count=300)
    timeline.on_reboot(seq=300, wall_time=60.0)

    reboot = timeline.reboots[-1]
    if isinstance(reboot, dict):
        assert reboot["seq"] == 300
        assert reboot["wall_time"] == 60.0
    else:
        assert reboot.seq == 300
        assert reboot.wall_time == 60.0

