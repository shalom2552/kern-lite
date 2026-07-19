"""
Live records view: a scrolling monospace table of every received record
(live and replay) with all decoded channels, alert and fault bytes.

file: dashboard/panels/records.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from groundstation.telemetry import channel_values

from dashboard import theme

MAX_VISIBLE = 600

_COLUMNS = ("time", "src", "seq", "lm35", "dht_t", "hum", "light", "pot", "alert", "fault")
_HEADINGS = {
    "time": "time", "src": "src", "seq": "seq", "lm35": "lm35 \N{DEGREE SIGN}C",
    "dht_t": "dht \N{DEGREE SIGN}C", "hum": "hum %", "light": "light %",
    "pot": "pot %", "alert": "alert", "fault": "fault",
}
_WIDTHS = {
    "time": 86, "src": 56, "seq": 60, "lm35": 72, "dht_t": 72, "hum": 66,
    "light": 72, "pot": 66, "alert": 62, "fault": 62,
}


class RecordsPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller, on_expand=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        bar = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8))
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(3, weight=1)

        ttk.Label(bar, text="LIVE RECORDS", style="Heading.TLabel").grid(row=0, column=0)
        self.count_var = tk.StringVar(value="0 records")
        ttk.Label(bar, textvariable=self.count_var, style="Muted.TLabel").grid(
            row=0, column=1, padx=(12, 0))
        self.pause_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Pause", variable=self.pause_var).grid(
            row=0, column=4, padx=(0, 8))
        ttk.Button(bar, text="Clear", command=self._clear).grid(row=0, column=5)
        if on_expand is not None:
            ttk.Button(bar, text="Expand \N{NORTH EAST ARROW}",
                       command=on_expand).grid(row=0, column=6, padx=(8, 0))

        wrap = ttk.Frame(self, style="Card.TFrame", padding=1)
        wrap.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(wrap, columns=_COLUMNS, show="headings",
                                 style="Mono.Treeview")
        for column in _COLUMNS:
            anchor = "w" if column in ("time", "src") else "e"
            self.tree.heading(column, text=_HEADINGS[column])
            self.tree.column(column, width=_WIDTHS[column], anchor=anchor,
                             stretch=(column == "fault"))
        self.tree.tag_configure("live", foreground=theme.COLOR_TEXT)
        self.tree.tag_configure("replay", foreground=theme.COLOR_AMBER)
        self.tree.tag_configure("alert", foreground=theme.COLOR_RED)

        scrollbar = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._seen = 0

    def _clear(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._seen = self.controller.telemetry.record_count

    def reset(self) -> None:
        self._clear()

    def _insert(self, row) -> None:
        record = row.record
        values = channel_values(record)
        tag = "replay" if row.source == "replay" else "live"
        if record.alert_bits:
            tag = "alert"
        self.tree.insert("", 0, tags=(tag,), values=(
            time.strftime("%H:%M:%S", time.localtime(row.wall_time)),
            row.source, record.seq,
            f"{values['lm35']:.1f}", f"{values['dht_temp']:.1f}",
            f"{values['dht_hum']:.1f}", f"{values['light'] * 100:.1f}",
            f"{values['pot'] * 100:.1f}",
            f"0x{record.alert_bits:02X}", f"0x{record.fault_bits:02X}"))

    def refresh(self) -> None:
        telemetry = self.controller.telemetry
        total = telemetry.record_count
        self.count_var.set(f"{total} records")
        if self.pause_var.get() or total == self._seen:
            return

        new = min(total - self._seen, len(telemetry.history))
        for row in list(telemetry.history)[-new:]:
            self._insert(row)
        self._seen = total

        children = self.tree.get_children()
        for item in children[MAX_VISIBLE:]:
            self.tree.delete(item)
