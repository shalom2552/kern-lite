"""
Session state timeline for the ground station: state bands with wall-clock
times and record counts, an alert track, reboot events, and a human-readable
text export.

file: groundstation/timeline.py
author: shalom2552
date: 2026-07-13
"""
from __future__ import annotations

import time

from .state import DeviceStateModel


def _fmt_time(wall: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(wall))


class StateTimeline:
    """Sequence of state segments; the last one stays open until the next
    transition. Alerts and reboots are tracked alongside."""

    def __init__(self) -> None:
        self.segments: list[dict] = []
        self.alerts: list[dict] = []
        self.reboots: list[dict] = []
        self._last_wall: float | None = None

    def on_state_change(self, from_state: int, to_state: int,
                        wall_time: float, session_record_count: int) -> None:
        """Close the open segment at this transition and start a new one."""
        self._close_open(wall_time, session_record_count)
        self.segments.append({
            "state": to_state,
            "start_wall": wall_time,
            "end_wall": None,
            "duration_s": None,
            "start_seq": session_record_count,
            "end_seq": None,
            "record_count": None,
        })
        self._last_wall = wall_time

    def on_alert(self, channel: str, active: bool, seq: int, wall_time: float) -> None:
        self.alerts.append({
            "channel": channel,
            "active": active,
            "seq": seq,
            "wall_time": wall_time,
        })
        self._last_wall = wall_time

    def on_reboot(self, seq: int, wall_time: float) -> None:
        self.reboots.append({"seq": seq, "wall_time": wall_time})
        self._last_wall = wall_time

    def export_text(self, path: str, now: float | None = None) -> None:
        """Write the timeline as text: one line per state band, then the
        alert track, then reboot events. The still-open band uses `now`
        (default: last event time) as its provisional end."""
        end = now if now is not None else self._last_wall

        lines = ["State timeline", "=============="]
        for seg in self.segments:
            state = DeviceStateModel.state_name(seg["state"])
            if seg["end_wall"] is not None:
                lines.append(
                    f"{_fmt_time(seg['start_wall'])} - {_fmt_time(seg['end_wall'])}  "
                    f"{state:<10} {seg['duration_s']:8.1f} s  "
                    f"records {seg['start_seq']}..{seg['end_seq']} ({seg['record_count']})"
                )
            else:
                duration = (end - seg["start_wall"]) if end is not None else 0.0
                lines.append(
                    f"{_fmt_time(seg['start_wall'])} - (open)    "
                    f"{state:<10} {duration:8.1f} s  "
                    f"records {seg['start_seq']}.. (open)"
                )

        lines += ["", "Alerts", "======"]
        for a in self.alerts:
            word = "ACTIVE" if a["active"] else "CLEAR"
            lines.append(f"{_fmt_time(a['wall_time'])}  {a['channel']:<10} {word:<6} seq={a['seq']}")

        lines += ["", "Reboots", "======="]
        for r in self.reboots:
            lines.append(f"{_fmt_time(r['wall_time'])}  seq={r['seq']}")

        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")

    def _close_open(self, wall_time: float, session_record_count: int) -> None:
        if not self.segments or self.segments[-1]["end_wall"] is not None:
            return
        seg = self.segments[-1]
        seg["end_wall"] = wall_time
        seg["duration_s"] = wall_time - seg["start_wall"]
        seg["end_seq"] = session_record_count
        seg["record_count"] = session_record_count - seg["start_seq"]
