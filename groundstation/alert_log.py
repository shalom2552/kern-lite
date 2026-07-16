"""
Unified ground station event/alert history: one time-ordered list of
categorized entries with wall time, session seq, and message, plus filtering
and a text export.

file: groundstation/alert_log.py
author: shalom2552
date: 2026-07-13
"""
from __future__ import annotations

import time
from dataclasses import dataclass

CATEGORIES = (
    "ALERT_ACTIVE",
    "ALERT_CLEAR",
    "STATE_TRANSITION",
    "NACK",
    "CRC_ERROR",
    "SYNC_ERROR",
    "SEQ_GAP",
    "STORAGE_CORRUPTION_WARNING",
    "REBOOT",
    "HEARTBEAT_TIMEOUT",
    "GS_EVENT",
)


@dataclass
class LogEntry:
    category: str
    wall_time: float
    session_seq: int | None
    message: str


class AlertLog:
    def __init__(self) -> None:
        self.entries: list[LogEntry] = []

    def add(self, category: str, message: str = "", session_seq: int | None = None,
            wall_time: float | None = None, **fields) -> LogEntry:
        """Append an entry. Extra keyword fields are folded into the message
        as 'key=value' pairs (e.g. add("NACK", code=..., command=...))."""
        if category not in CATEGORIES:
            raise ValueError(f"unknown alert log category: {category}")

        if fields:
            # enums render by name (NackCode.InvalidState -> "InvalidState")
            extra = " ".join(f"{k}={getattr(v, 'name', v)}" for k, v in fields.items())
            message = f"{message} {extra}".strip()

        entry = LogEntry(
            category=category,
            wall_time=wall_time if wall_time is not None else time.time(),
            session_seq=session_seq,
            message=message,
        )
        self.entries.append(entry)
        return entry

    def filter(self, category_set) -> list[LogEntry]:
        """Entries whose category is in category_set, in current order."""
        wanted = set(category_set)
        return [e for e in self.entries if e.category in wanted]

    def sort_by_time(self) -> list[LogEntry]:
        """Sort the log in place by wall time and return it."""
        self.entries.sort(key=lambda e: e.wall_time)
        return self.entries

    def export_text(self, path: str) -> None:
        with open(path, "w") as f:
            for e in self.entries:
                stamp = time.strftime("%H:%M:%S", time.localtime(e.wall_time))
                seq = "-" if e.session_seq is None else str(e.session_seq)
                f.write(f"{stamp}  {e.category:<18} seq={seq:<6} {e.message}\n")
