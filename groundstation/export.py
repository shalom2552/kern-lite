"""
Ground station export functions: session records to CSV (scaled values,
spreadsheet-friendly headers), and text exports for the alert log, raw frame
log, and state timeline.

file: groundstation/export.py
author: shalom2552
date: 2026-07-13
"""
from __future__ import annotations

import csv
import os
import time

from .state import DeviceStateModel

_CSV_HEADERS = [
    "wall_time", "seq", "timestamp_s", "ms",
    "lm35_celsius", "dht_temp_celsius", "dht_humidity_pct",
    "light_normalized", "pot_normalized",
    "alert_bits", "state", "fault_bits",
]


def session_to_csv(session, path: str) -> None:
    """Write every session record with all fields scaled to display units."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_HEADERS)
        for rec, wall in zip(session.records, session.wall_times):
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(wall)),
                rec.seq, rec.timestamp, rec.ms,
                f"{rec.lm35_celsius:.1f}",
                f"{rec.dht_temp_celsius:.1f}",
                f"{rec.dht_humidity:.1f}",
                f"{rec.light_normalized:.4f}",
                f"{rec.pot_normalized:.4f}",
                f"0x{rec.alert_bits:02X}",
                DeviceStateModel.state_name(rec.state),
                f"0x{rec.fault_bits:02X}",
            ])


def alert_log_to_text(alert_log, path: str) -> None:
    alert_log.export_text(path)


def timeline_to_text(timeline, path: str, now: float | None = None) -> None:
    timeline.export_text(path, now=now)


def raw_frame_log_to_text(session, path: str) -> None:
    """Reformat the session's frames.log ('wall direction hex' lines) into a
    readable listing with timestamps and frame lengths."""
    lines_out = []
    frames_path = os.path.join(session.dir, "frames.log") if session.dir else None

    if frames_path and os.path.isfile(frames_path):
        with open(frames_path) as f:
            for line in f:
                parts = line.split()
                if len(parts) != 3:
                    continue
                wall, direction, hexstr = parts
                stamp = time.strftime("%H:%M:%S", time.localtime(float(wall)))
                lines_out.append(f"{stamp}  {direction:<2} len={len(hexstr) // 2:<4} {hexstr}")
    else:
        lines_out.append("(no frames.log found for this session)")

    with open(path, "w") as f:
        f.write("\n".join(lines_out) + "\n")
