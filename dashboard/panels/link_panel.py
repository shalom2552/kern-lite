"""
Link panel: RX/TX/error counters, latency, NACK rate, and the 0-100
link-quality score with a colored bar (FR-GS-02/17).

file: dashboard/panels/link_panel.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class LinkPanel(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent, text="Link", padding=10)
        self.controller = controller
        self.columnconfigure(1, weight=1)

        self.vars = {key: tk.StringVar(value="-") for key in
                     ("traffic", "errors", "nack", "latency", "quality")}

        rows = [
            ("Traffic", "traffic"),
            ("Errors", "errors"),
            ("NACKs", "nack"),
            ("Latency", "latency"),
            ("Quality", "quality"),
        ]
        for row, (label, key) in enumerate(rows):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(self, textvariable=self.vars[key], style="Metric.TLabel").grid(
                row=row, column=1, sticky="e", pady=2)

        self.quality_bar = ttk.Progressbar(self, maximum=100.0,
                                           style="Ok.Horizontal.TProgressbar")
        self.quality_bar.grid(row=len(rows), column=0, columnspan=2,
                              sticky="ew", pady=(6, 0))

    def refresh(self) -> None:
        link = self.controller.link
        quality = self.controller.quality

        self.vars["traffic"].set(f"rx {link.rx_count} / tx {link.tx_count}")
        self.vars["errors"].set(f"crc {link.crc_error_count} / sync {link.sync_error_count}")
        self.vars["nack"].set(f"{link.nack_count} ({link.nack_rate * 100:.0f}%)")

        last = link.last_latency_ms
        avg = link.rolling_avg_latency_ms
        if last is None:
            self.vars["latency"].set("-")
        else:
            self.vars["latency"].set(f"{last:.0f} ms (avg {avg:.0f} ms)")

        self.vars["quality"].set(f"{quality.quality_pct:.0f}%")
        self.quality_bar["value"] = quality.quality_pct
        if quality.poor:
            bar_style = "Danger.Horizontal.TProgressbar"
        elif quality.degraded:
            bar_style = "Warn.Horizontal.TProgressbar"
        else:
            bar_style = "Ok.Horizontal.TProgressbar"
        self.quality_bar.configure(style=bar_style)
