"""
Storage panel: device state, SD-mounted flag, ring counters (file count,
active file, write index, total records, wraps), live/replay record counts,
and a drawn view of the 4-file ring (FR-GS-11).

file: dashboard/panels/storage.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from groundstation.state import DeviceStateModel
from groundstation.storage_panel import RECORDS_PER_FILE

from dashboard import theme


class StoragePanel(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent, text="Device & storage", padding=10)
        self.controller = controller
        self.columnconfigure(1, weight=1)

        keys = ("state", "sd", "files", "windex", "total", "wraps", "live", "replay")
        self.vars = {key: tk.StringVar(value="-") for key in keys}

        rows = [
            ("Device state", "state"),
            ("SD mounted", "sd"),
            ("Active file", "files"),
            ("Write index", "windex"),
            ("Total records", "total"),
            ("Ring wraps", "wraps"),
            ("Live records", "live"),
            ("Replay records", "replay"),
        ]
        for row, (label, key) in enumerate(rows):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=1)
            ttk.Label(self, textvariable=self.vars[key], style="Metric.TLabel").grid(
                row=row, column=1, sticky="e", pady=1)

        self.ring = tk.Canvas(self, height=54, bg=theme.COLOR_INPUT,
                              highlightthickness=1,
                              highlightbackground=theme.COLOR_BORDER, bd=0)
        self.ring.grid(row=len(rows), column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def refresh(self) -> None:
        storage = self.controller.storage_model
        state_name = DeviceStateModel.state_name(self.controller.state_model.state)

        self.vars["state"].set(state_name)
        self.vars["sd"].set("yes" if storage.sd_mounted else "no")
        self.vars["files"].set(f"{storage.current_file} / {storage.file_count or 4}")
        self.vars["windex"].set(str(storage.records_in_file))
        self.vars["total"].set(str(storage.total_records))
        self.vars["wraps"].set(str(storage.wrap_count))
        self.vars["live"].set(str(storage.live_record_count))
        self.vars["replay"].set(str(storage.replay_record_count))

        self._draw_ring(storage.ring_visual())

    def _draw_ring(self, files: list[dict]) -> None:
        canvas = self.ring
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        if not files:
            return

        gap = 6
        slot_w = (width - gap * (len(files) + 1)) / len(files)
        for entry in files:
            x0 = gap + entry["index"] * (slot_w + gap)
            x1 = x0 + slot_w
            fill_frac = min(1.0, entry["record_count"] / RECORDS_PER_FILE)
            outline = theme.COLOR_ACCENT if entry["is_current"] else theme.COLOR_BORDER

            canvas.create_rectangle(x0, 8, x1, height - 16, outline=outline, width=2)
            if fill_frac > 0:
                fill_color = theme.COLOR_ACCENT if entry["is_current"] else "#2d4a3e"
                canvas.create_rectangle(
                    x0 + 2, (height - 16) - (height - 24) * fill_frac,
                    x1 - 2, height - 18, fill=fill_color, outline="")
            canvas.create_text((x0 + x1) / 2, height - 8,
                               text=f"F{entry['index']} {entry['record_count']}",
                               fill=theme.COLOR_MUTED, font=theme.font(8))
