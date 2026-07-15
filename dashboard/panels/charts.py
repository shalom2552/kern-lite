"""
Charts panel: the five telemetry channels rendered by RollingChart onto a
single embedded matplotlib figure, with visibility toggles (FR-GS-10).
RollingChart.render already draws thresholds, alert shading, and
state/reboot/gap markers.

file: dashboard/panels/charts.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from groundstation.telemetry import CHANNELS

from dashboard import theme


class ChartsPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent)
        self.controller = controller
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self._compact: bool | None = None
        toggles = ttk.Frame(self, style="Panel.TFrame")
        toggles.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.toggle_vars: dict[str, tk.BooleanVar] = {}
        self._toggle_buttons: list[ttk.Checkbutton] = []
        for channel in CHANNELS:
            var = tk.BooleanVar(value=True)
            self.toggle_vars[channel] = var
            self._toggle_buttons.append(
                ttk.Checkbutton(toggles, text=theme.CHANNEL_LABELS[channel], variable=var,
                                command=lambda c=channel: self._toggle(c)))
        self.set_compact(False)

        self.figure = Figure(figsize=(6, 4), dpi=100, facecolor=theme.COLOR_BG)
        axes = self.figure.subplots(len(CHANNELS), 1, sharex=True)
        self.ax_dict = dict(zip(CHANNELS, axes))
        for ax in axes:
            self._style_axis(ax)
        self.figure.subplots_adjust(left=0.08, right=0.985, top=0.98,
                                    bottom=0.06, hspace=0.35)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        self._drawn_count = -1

    def set_compact(self, compact: bool) -> None:
        """Toggles in one row on wide screens, two rows on narrow ones."""
        if compact == self._compact:
            return
        self._compact = compact
        per_row = 3 if compact else len(self._toggle_buttons)
        for i, button in enumerate(self._toggle_buttons):
            button.grid(row=i // per_row, column=i % per_row,
                        sticky="w", padx=(0, 12))

    def _style_axis(self, ax) -> None:
        ax.set_facecolor(theme.COLOR_INPUT)
        ax.tick_params(colors=theme.COLOR_TEXT, labelsize=10)
        ax.yaxis.label.set_color(theme.COLOR_TEXT)
        ax.yaxis.label.set_size(11)
        ax.grid(True, color=theme.COLOR_BORDER_SOFT, linewidth=0.6, alpha=0.6)
        for spine in ax.spines.values():
            spine.set_color(theme.COLOR_BORDER)

    def _toggle(self, channel: str) -> None:
        self.controller.chart.toggle_channel(channel)
        self._drawn_count = -1

    def refresh(self) -> None:
        chart = self.controller.chart
        count = self.controller.telemetry.record_count
        if count == self._drawn_count:
            return
        self._drawn_count = count

        chart.render(self.ax_dict)
        for ax in self.ax_dict.values():
            self._style_axis(ax)
            lines = ax.get_lines()
            if lines:
                lines[0].set_color(theme.COLOR_ACCENT2)
                lines[0].set_linewidth(2.2)
        self.canvas.draw_idle()
