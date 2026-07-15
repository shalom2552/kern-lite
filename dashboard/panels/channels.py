"""
Live channels panel: current value with units and alert flag per channel
(FR-GS-08) plus the full incremental statistics line: min/max (with seq),
mean, stddev, alert activations, time in alert, percent in alert (FR-GS-09).

file: dashboard/panels/channels.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from groundstation.chart import CHANNEL_THRESHOLDS
from groundstation.telemetry import ALERT_MASKS, CHANNELS, channel_values

from dashboard.theme import CHANNEL_LABELS, CHANNEL_RANGES, format_channel_value


class ChannelsPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent)
        self.controller = controller
        self.columnconfigure(0, weight=1)

        self.rows: dict[str, dict[str, object]] = {}
        for row, channel in enumerate(CHANNELS):
            self._build_row(row, channel)

    def _build_row(self, row: int, channel: str) -> None:
        lo, hi = CHANNEL_THRESHOLDS[channel]
        frame = ttk.LabelFrame(self, text=f"{CHANNEL_LABELS[channel]}   "
                                          f"(thresholds {lo:g} to {hi:g})", padding=10)
        pady = (0, 8) if row < len(CHANNELS) - 1 else (0, 0)
        frame.grid(row=row, column=0, sticky="ew", pady=pady)
        frame.columnconfigure(1, weight=1)

        value_var = tk.StringVar(value="-")
        ttk.Label(frame, textvariable=value_var, style="Metric.TLabel",
                  width=12).grid(row=0, column=0, sticky="w")

        progress = ttk.Progressbar(frame, maximum=100.0, style="Ok.Horizontal.TProgressbar")
        progress.grid(row=0, column=1, sticky="ew", padx=10)

        alert_var = tk.StringVar(value="normal")
        alert_label = ttk.Label(frame, textvariable=alert_var, width=8)
        alert_label.grid(row=0, column=2, sticky="e")

        stats_var = tk.StringVar(value="no samples yet")
        ttk.Label(frame, textvariable=stats_var, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.rows[channel] = {
            "value": value_var,
            "progress": progress,
            "alert": alert_var,
            "alert_label": alert_label,
            "stats": stats_var,
        }

    def refresh(self) -> None:
        latest = self.controller.telemetry.latest
        values = channel_values(latest) if latest is not None else {}

        for channel in CHANNELS:
            row = self.rows[channel]
            value = values.get(channel)

            if value is None:
                row["value"].set("-")
                row["progress"]["value"] = 0.0
                row["alert"].set("normal")
                row["alert_label"].configure(style="TLabel")
            else:
                hi_mask, lo_mask = ALERT_MASKS[channel]
                alert = bool(latest.alert_bits & (hi_mask | lo_mask))
                row["value"].set(format_channel_value(channel, value))
                row["progress"]["value"] = self._scale(channel, value)
                row["progress"].configure(
                    style="Danger.Horizontal.TProgressbar" if alert
                    else "Ok.Horizontal.TProgressbar")
                row["alert"].set("ALERT" if alert else "normal")
                row["alert_label"].configure(style="Alert.TLabel" if alert else "TLabel")

            stats = self.controller.stats.channels[channel]
            if stats.n:
                row["stats"].set(
                    f"min {stats.min_val:.2f} (seq {stats.min_seq})  "
                    f"max {stats.max_val:.2f} (seq {stats.max_seq})  "
                    f"mean {stats.mean:.2f}  std {stats.stddev:.2f}  |  "
                    f"alerts {stats.alert_activations}  "
                    f"in-alert {stats.time_in_alert_s:.1f}s ({stats.pct_in_alert:.1f}%)")
            else:
                row["stats"].set("no samples yet")

    @staticmethod
    def _scale(channel: str, value: float) -> float:
        lo, hi = CHANNEL_RANGES[channel]
        if hi <= lo:
            return 0.0
        return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100.0))
