"""
Timeline panel: session state bands over wall time with alert and reboot
ticks, a compact stats strip (current state, time in state), and a full-width
session log of transitions, commands, alerts, and reboots.

file: dashboard/panels/timeline_panel.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from groundstation.telemetry import CHANNELS

from dashboard import theme
from dashboard.theme import CHANNEL_LABELS

BAND_TOP = 26
BAND_HEIGHT = 54
ALERT_TRACK_Y = 96
PAD_X = 54
STATE_NAMES = {0: "Idle", 1: "Recording", 2: "Fault"}


class TimelinePanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent)
        self.controller = controller
        self._narrow: bool | None = None

        band = ttk.Frame(self, style="Card.TFrame", padding=1)
        band.grid(row=0, column=0, columnspan=4, sticky="ew")
        band.columnconfigure(0, weight=1)
        band.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(band, height=150, bg=theme.COLOR_CARD,
                                highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.legend = _LegendCard(self)
        self.status = _StatusCard(self)
        self.channel_alerts = _ChannelAlertsCard(self)
        self.log = _LogCard(self)

        self.set_narrow(False)

    def set_narrow(self, narrow: bool) -> None:
        """Cards in one row on wide screens, stacked two-up on narrow ones."""
        if narrow == self._narrow:
            return
        self._narrow = narrow
        for card in (self.legend, self.status, self.channel_alerts, self.log):
            card.grid_forget()
        if narrow:
            for col, weight in enumerate((1, 1, 0, 0)):
                self.columnconfigure(col, weight=weight)
            self.rowconfigure(1, weight=0)
            self.rowconfigure(2, weight=0)
            self.rowconfigure(3, weight=1)
            self.legend.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
            self.status.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(10, 0))
            self.channel_alerts.grid(row=2, column=0, columnspan=2,
                                     sticky="nsew", pady=(10, 0))
            self.log.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        else:
            for col, weight in enumerate((0, 2, 3, 3)):
                self.columnconfigure(col, weight=weight)
            self.rowconfigure(1, weight=1)
            self.rowconfigure(2, weight=0)
            self.rowconfigure(3, weight=0)
            self.legend.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
            self.status.grid(row=1, column=1, sticky="nsew", padx=10, pady=(10, 0))
            self.channel_alerts.grid(row=1, column=2, sticky="nsew",
                                     padx=(0, 10), pady=(10, 0))
            self.log.grid(row=1, column=3, sticky="nsew", pady=(10, 0))

    def reset(self) -> None:
        self.log.reset()

    def refresh(self) -> None:
        self._draw_band()
        self.status.refresh(self.controller.timeline)
        self.channel_alerts.refresh(self.controller.stats)
        self.log.refresh(self.controller.alert_log)

    def _draw_band(self) -> None:
        timeline = self.controller.timeline
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        now = time.time()

        if not timeline.segments:
            canvas.create_text(width / 2, height / 2, text="no session activity yet",
                               fill=theme.COLOR_MUTED, font=theme.font(10))
            return

        t0 = timeline.segments[0]["start_wall"]
        span = max(now - t0, 1.0)
        plot_w = max(width - 2 * PAD_X, 1)

        def x_of(wall: float) -> float:
            return PAD_X + (wall - t0) / span * plot_w

        canvas.create_line(PAD_X, BAND_TOP + BAND_HEIGHT + 1,
                           width - PAD_X, BAND_TOP + BAND_HEIGHT + 1,
                           fill=theme.COLOR_BORDER_SOFT)

        for seg in timeline.segments:
            end = seg["end_wall"] if seg["end_wall"] is not None else now
            x0, x1 = x_of(seg["start_wall"]), x_of(end)
            color = theme.STATE_COLORS.get(seg["state"], theme.COLOR_MUTED)
            canvas.create_rectangle(x0, BAND_TOP, max(x1, x0 + 2), BAND_TOP + BAND_HEIGHT,
                                    fill=color, outline=theme.COLOR_CARD, width=1)
            if x1 - x0 > 64:
                duration = end - seg["start_wall"]
                canvas.create_text(
                    (x0 + x1) / 2, BAND_TOP + BAND_HEIGHT / 2,
                    text=f"{STATE_NAMES.get(seg['state'], '?')}  {duration:.0f}s",
                    fill=theme.COLOR_BG, font=theme.font(9, "bold"))

        canvas.create_text(PAD_X - 8, ALERT_TRACK_Y + 6, anchor="e", text="alerts",
                           fill=theme.COLOR_FAINT, font=theme.font(8))
        for alert in timeline.alerts:
            x = x_of(alert["wall_time"])
            color = theme.COLOR_RED if alert["active"] else theme.COLOR_ACCENT2
            canvas.create_line(x, ALERT_TRACK_Y, x, ALERT_TRACK_Y + 14, fill=color, width=2)

        for reboot in timeline.reboots:
            x = x_of(reboot["wall_time"])
            canvas.create_line(x, BAND_TOP - 8, x, ALERT_TRACK_Y + 14,
                               fill=theme.COLOR_TEXT, width=1, dash=(2, 2))
            canvas.create_text(x, BAND_TOP - 14, text="reboot",
                               fill=theme.COLOR_TEXT, font=theme.font(8))

        for wall in (t0, now):
            canvas.create_text(x_of(wall), BAND_TOP + BAND_HEIGHT + 14,
                               text=time.strftime("%H:%M:%S", time.localtime(wall)),
                               fill=theme.COLOR_MUTED, font=theme.font(8))


class _LegendCard(ttk.Frame):
    _ITEMS = (
        (0, "Idle"), (1, "Recording"), (2, "Fault"),
        (theme.COLOR_RED, "Alert set"), (theme.COLOR_ACCENT2, "Alert clear"),
        (theme.COLOR_TEXT, "Reboot"),
    )

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Card.TFrame", padding=14)
        ttk.Label(self, text="LEGEND", style="Heading.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        for i, (key, label) in enumerate(self._ITEMS):
            color = theme.STATE_COLORS[key] if isinstance(key, int) else key
            swatch = tk.Canvas(self, width=14, height=14, bg=color,
                               highlightthickness=0, bd=0)
            swatch.grid(row=1 + i, column=0, sticky="w", pady=4)
            ttk.Label(self, text=label, style="CardMuted.TLabel").grid(
                row=1 + i, column=1, sticky="w", padx=(8, 0), pady=4)


class _StatusCard(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Card.TFrame", padding=16)
        self.columnconfigure(1, weight=1)
        ttk.Label(self, text="STATUS", style="Heading.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self.pill = ttk.Label(self, text="-", style="Pill.TLabel")
        self.pill.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 14))

        self._metric_vars: dict[str, tk.StringVar] = {}
        for i, (label, key) in enumerate((("Open for", "open"),
                                          ("Alerts", "alerts"),
                                          ("Reboots", "reboots"))):
            ttk.Label(self, text=label, style="CardMuted.TLabel").grid(
                row=2 + i, column=0, sticky="w", pady=3)
            var = tk.StringVar(value="-")
            self._metric_vars[key] = var
            ttk.Label(self, textvariable=var, style="CardMetric.TLabel").grid(
                row=2 + i, column=1, sticky="e", pady=3)

        ttk.Separator(self, orient="horizontal").grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(self, text="TIME IN STATE", style="CardMuted.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self._state_vars: dict[int, tk.StringVar] = {}
        for i, state in enumerate((0, 1, 2)):
            dot = tk.Canvas(self, width=10, height=10, bg=theme.STATE_COLORS[state],
                            highlightthickness=0, bd=0)
            dot.grid(row=7 + i, column=0, sticky="w", pady=3)
            ttk.Label(self, text=STATE_NAMES[state], style="Card.TLabel").grid(
                row=7 + i, column=0, sticky="w", padx=(20, 0), pady=3)
            var = tk.StringVar(value="-")
            self._state_vars[state] = var
            ttk.Label(self, textvariable=var, style="CardMetric.TLabel").grid(
                row=7 + i, column=1, sticky="e", pady=3)

    def refresh(self, timeline) -> None:
        now = time.time()
        if not timeline.segments:
            self.pill.configure(text="NO SESSION", style="Pill.TLabel")
            self._metric_vars["open"].set("-")
            self._metric_vars["alerts"].set("0")
            self._metric_vars["reboots"].set("0")
            for var in self._state_vars.values():
                var.set("-")
            return

        seg = timeline.segments[-1]
        state = seg["state"]
        styles = {0: "Pill.TLabel", 1: "PillOk.TLabel", 2: "PillBad.TLabel"}
        self.pill.configure(text=STATE_NAMES.get(state, "?").upper(),
                            style=styles.get(state, "Pill.TLabel"))
        self._metric_vars["open"].set(f"{now - seg['start_wall']:.0f}s")
        self._metric_vars["alerts"].set(str(len(timeline.alerts)))
        self._metric_vars["reboots"].set(str(len(timeline.reboots)))

        totals = {0: 0.0, 1: 0.0, 2: 0.0}
        visits = {0: 0, 1: 0, 2: 0}
        for s in timeline.segments:
            end = s["end_wall"] if s["end_wall"] is not None else now
            totals[s["state"]] = totals.get(s["state"], 0.0) + (end - s["start_wall"])
            visits[s["state"]] = visits.get(s["state"], 0) + 1
        for state in (0, 1, 2):
            self._state_vars[state].set(
                f"{totals[state]:.0f}s  \N{MULTIPLICATION SIGN}{visits[state]}")


class _ChannelAlertsCard(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Card.TFrame", padding=14)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="CHANNEL ALERTS", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8))

        columns = ("channel", "n", "acts", "in_alert", "pct")
        headings = {"channel": "channel", "n": "samples", "acts": "activations",
                    "in_alert": "in alert", "pct": "% alert"}
        self.tree = ttk.Treeview(self, columns=columns, show="headings",
                                 height=len(CHANNELS))
        for column, width, anchor in (("channel", 130, "w"), ("n", 80, "e"),
                                      ("acts", 90, "e"), ("in_alert", 90, "e"),
                                      ("pct", 80, "e")):
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=width, anchor=anchor,
                             stretch=(column == "channel"))
        self.tree.tag_configure("alerting", foreground=theme.COLOR_RED)
        self.tree.grid(row=1, column=0, sticky="nsew")

    def refresh(self, stats) -> None:
        self.tree.delete(*self.tree.get_children())
        for channel in CHANNELS:
            s = stats.channels[channel]
            tag = ("alerting",) if s.alert_active else ()
            self.tree.insert("", "end", tags=tag, values=(
                CHANNEL_LABELS[channel], s.n, s.alert_activations,
                f"{s.time_in_alert_s:.1f}s", f"{s.pct_in_alert:.1f}%"))


class _LogCard(ttk.Frame):
    _CATEGORIES = ("STATE_TRANSITION", "ALERT_ACTIVE", "ALERT_CLEAR", "REBOOT",
                   "HEARTBEAT_TIMEOUT", "GS_EVENT")
    _TAGS = {
        "STATE_TRANSITION": "state",
        "ALERT_ACTIVE": "active",
        "ALERT_CLEAR": "clear",
        "REBOOT": "reboot",
        "HEARTBEAT_TIMEOUT": "reboot",
        "GS_EVENT": "event",
    }

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Card.TFrame", padding=14)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="SESSION LOG", style="Heading.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8))

        columns = ("time", "event", "detail")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        for column, width, anchor in (("time", 90, "w"), ("event", 170, "w"),
                                      ("detail", 300, "w")):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, anchor=anchor,
                             stretch=(column == "detail"))
        self.tree.tag_configure("state", foreground=theme.COLOR_ACCENT)
        self.tree.tag_configure("active", foreground=theme.COLOR_RED)
        self.tree.tag_configure("clear", foreground=theme.COLOR_ACCENT2)
        self.tree.tag_configure("reboot", foreground=theme.COLOR_AMBER)
        self.tree.tag_configure("event", foreground=theme.COLOR_MUTED)

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        self._rendered = 0

    def reset(self) -> None:
        self._rendered = 0
        self.tree.delete(*self.tree.get_children())

    def refresh(self, alert_log) -> None:
        entries = alert_log.entries
        if len(entries) == self._rendered:
            return
        for entry in entries[self._rendered:]:
            if entry.category not in self._CATEGORIES:
                continue
            if entry.category == "GS_EVENT" and entry.message == "sent STATUS":
                continue
            self.tree.insert("", 0, tags=(self._TAGS[entry.category],), values=(
                time.strftime("%H:%M:%S", time.localtime(entry.wall_time)),
                entry.category, entry.message))
        self._rendered = len(entries)
        for item in self.tree.get_children()[300:]:
            self.tree.delete(item)
