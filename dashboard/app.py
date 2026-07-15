"""
Dashboard application shell: window layout, menu (session load + exports),
frame-pump and refresh loops, and clean shutdown on window close or signal.

file: dashboard/app.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import logging
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from groundstation import export
from groundstation.session import Session
from groundstation.state import DeviceStateModel
from groundstation.telemetry import CHANNELS

from dashboard import theme
from dashboard.controller import DashboardController, rebuild_from_session
from dashboard.panels.channels import ChannelsPanel
from dashboard.panels.charts import ChartsPanel
from dashboard.panels.commands import CommandPanel
from dashboard.panels.connection import ConnectionPanel
from dashboard.panels.events import EventsPanel
from dashboard.panels.link_panel import LinkPanel
from dashboard.panels.records import RecordsPanel
from dashboard.panels.storage import StoragePanel
from dashboard.panels.timeline_panel import TimelinePanel

PUMP_INTERVAL_MS = 50
REFRESH_INTERVAL_MS = 250
CHART_INTERVAL_MS = 500


def _silence_groundstation_logging() -> None:
    gs_logger = logging.getLogger("groundstation")
    gs_logger.setLevel(logging.ERROR)
    if not any(isinstance(h, logging.NullHandler) for h in gs_logger.handlers):
        gs_logger.addHandler(logging.NullHandler())


class GroundStationApp(tk.Tk):
    def __init__(self, controller: DashboardController | None = None) -> None:
        _silence_groundstation_logging()
        super().__init__()
        self.title("KERN-LITE Ground Station")
        self.minsize(800, 600)
        self.geometry("800x600")

        self.controller = controller if controller is not None else DashboardController()
        self._shutting_down = False
        self._after_ids: list[str] = []
        self._extra_panels: list = []
        self._records_window: tk.Toplevel | None = None

        theme.apply_theme(self)
        self._build_menu()
        self._build_layout()

        self.protocol("WM_DELETE_WINDOW", self.shutdown)
        self._schedule(PUMP_INTERVAL_MS, self._pump_tick)
        self._schedule(REFRESH_INTERVAL_MS, self._refresh_tick)
        self._schedule(CHART_INTERVAL_MS, self._chart_tick)

    # -- construction -------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load session...", command=self._load_session)
        file_menu.add_separator()
        file_menu.add_command(label="Export records CSV...",
                              command=lambda: self._export("csv"))
        file_menu.add_command(label="Export alert log...",
                              command=lambda: self._export("alerts"))
        file_menu.add_command(label="Export timeline...",
                              command=lambda: self._export("timeline"))
        file_menu.add_command(label="Export raw frames...",
                              command=lambda: self._export("frames"))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.shutdown)
        menubar.add_cascade(label="File", menu=file_menu)
        self.configure(menu=menubar)

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(16, 12), style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)

        title_box = ttk.Frame(header, style="Panel.TFrame")
        title_box.grid(row=0, column=0, sticky="w", padx=(0, 24))
        ttk.Label(title_box, text="KERN-LITE", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(title_box, text="Ground Station Console",
                  style="Subtitle.TLabel").grid(row=1, column=0, sticky="w")

        self.connection = ConnectionPanel(header, self.controller,
                                          self._connect, self._disconnect)
        self.connection.grid(row=0, column=1, sticky="w")
        self.command_panel = CommandPanel(header, self.controller)
        self.command_panel.grid(row=0, column=3, sticky="e")

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew", padx=14, pady=(8, 14))

        live = ttk.Frame(notebook)
        live.columnconfigure(0, weight=3)
        live.columnconfigure(1, weight=2)
        live.rowconfigure(2, weight=1)
        notebook.add(live, text="Live")

        self.channels = ChannelsPanel(live, self.controller)
        self.channels.grid(row=0, column=0, sticky="new", padx=(0, 10))

        right = ttk.Frame(live)
        right.grid(row=0, column=1, sticky="new")
        right.columnconfigure(0, weight=1)
        self.storage = StoragePanel(right, self.controller)
        self.storage.grid(row=0, column=0, sticky="new")
        self.link_panel = LinkPanel(right, self.controller)
        self.link_panel.grid(row=1, column=0, sticky="new", pady=(10, 0))

        self.records = RecordsPanel(live, self.controller, on_expand=self._expand_records)
        self.records.grid(row=2, column=0, sticky="nsew", padx=(0, 10), pady=(14, 0))
        self.events = EventsPanel(live, self.controller)
        self.events.grid(row=2, column=1, sticky="nsew", pady=(14, 0))

        self.charts = ChartsPanel(notebook, self.controller)
        notebook.add(self.charts, text="Charts")

        self.timeline = TimelinePanel(notebook, self.controller)
        notebook.add(self.timeline, text="Timeline")

        self._live_panels = (self.connection, self.command_panel, self.channels,
                             self.storage, self.link_panel, self.events,
                             self.records, self.timeline)

    # -- loops --------------------------------------------------------------

    def _schedule(self, delay_ms: int, callback) -> None:
        if self._shutting_down:
            return
        self._after_ids.append(self.after(delay_ms, callback))

    def _pump_tick(self) -> None:
        try:
            self.controller.pump(time.time())
        finally:
            self._schedule(PUMP_INTERVAL_MS, self._pump_tick)

    def _refresh_tick(self) -> None:
        try:
            for panel in self._live_panels:
                panel.refresh()
            for panel in self._extra_panels:
                panel.refresh()
        finally:
            self._schedule(REFRESH_INTERVAL_MS, self._refresh_tick)

    def _expand_records(self) -> None:
        if self._records_window is not None:
            self._records_window.deiconify()
            self._records_window.lift()
            return

        window = tk.Toplevel(self)
        window.title("KERN-LITE - Live records")
        window.configure(bg=theme.COLOR_BG)
        window.geometry("800x600")
        window.rowconfigure(0, weight=1)
        window.columnconfigure(0, weight=1)

        panel = RecordsPanel(window, self.controller)
        panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self._extra_panels.append(panel)
        self._records_window = window

        def close() -> None:
            if panel in self._extra_panels:
                self._extra_panels.remove(panel)
            self._records_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close)

    def _chart_tick(self) -> None:
        try:
            self.charts.refresh()
        finally:
            self._schedule(CHART_INTERVAL_MS, self._chart_tick)

    # -- connection actions -------------------------------------------------

    def _connect(self, port: str) -> None:
        if not port:
            messagebox.showwarning("No port", "Choose a serial port first.", parent=self)
            return
        try:
            session_dir = self.controller.connect(port)
        except Exception as exc:
            messagebox.showerror("Connect failed", str(exc), parent=self)
            return
        self.title(f"KERN-LITE Ground Station - {port} - {session_dir}")

    def _disconnect(self) -> None:
        self.controller.disconnect()
        self.title("KERN-LITE Ground Station")

    # -- session load / export ----------------------------------------------

    def _load_session(self) -> None:
        path = filedialog.askdirectory(title="Choose a session directory",
                                       initialdir="sessions", parent=self)
        if not path:
            return
        try:
            session = Session.load(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Load failed", str(exc), parent=self)
            return
        SessionViewer(self, session)

    def _export(self, kind: str) -> None:
        controller = self.controller
        specs = {
            "csv": ("records.csv", ".csv",
                    lambda p: export.session_to_csv(controller.session, p)),
            "alerts": ("alerts.log", ".log",
                       lambda p: export.alert_log_to_text(controller.alert_log, p)),
            "timeline": ("timeline.log", ".log",
                         lambda p: export.timeline_to_text(controller.timeline, p)),
            "frames": ("frames.txt", ".txt",
                       lambda p: export.raw_frame_log_to_text(controller.session, p)),
        }
        default_name, ext, write = specs[kind]
        path = filedialog.asksaveasfilename(initialfile=default_name,
                                            defaultextension=ext, parent=self)
        if not path:
            return
        try:
            write(path)
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)
            return
        messagebox.showinfo("Export complete", f"Wrote {path}", parent=self)

    # -- shutdown -----------------------------------------------------------

    def shutdown(self) -> None:
        """Idempotent: cancel loops, close the link and session files, then
        tear down the window. Safe to call from WM_DELETE_WINDOW, the File
        menu, a signal handler, or a finally block."""
        if self._shutting_down:
            return
        self._shutting_down = True

        for after_id in self._after_ids:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._after_ids.clear()

        self.controller.shutdown()

        try:
            self.destroy()
        except tk.TclError:
            pass  # window already gone


class SessionViewer(tk.Toplevel):
    """Offline viewer for a loaded session: rebuilt charts and per-channel
    statistics, clearly separated from the live view (FR-GS-15)."""

    def __init__(self, parent: tk.Misc, session: Session) -> None:
        super().__init__(parent)
        self.title(f"Loaded session - {session.dir or 'unknown'}")
        self.minsize(900, 640)
        self.configure(bg=theme.COLOR_BG)
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        stats, chart = rebuild_from_session(session)

        banner = ttk.Label(
            self, style="StatusWarn.TLabel",
            text=(f"LOADED SESSION (not live) - {len(session.records)} records - "
                  f"{session.dir or ''}"))
        banner.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))

        columns = ("channel", "n", "min", "max", "mean", "std",
                   "alerts", "in_alert_s", "pct")
        tree = ttk.Treeview(self, columns=columns, show="headings",
                            height=len(CHANNELS))
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=90, anchor="center")
        for channel in CHANNELS:
            s = stats.channels[channel]
            if s.n:
                tree.insert("", "end", values=(
                    channel, s.n, f"{s.min_val:.2f}", f"{s.max_val:.2f}",
                    f"{s.mean:.2f}", f"{s.stddev:.2f}", s.alert_activations,
                    f"{s.time_in_alert_s:.1f}", f"{s.pct_in_alert:.1f}%"))
            else:
                tree.insert("", "end", values=(channel, 0, "-", "-", "-", "-", 0, "-", "-"))
        tree.grid(row=1, column=0, sticky="ew", padx=10, pady=10)

        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure

        figure = Figure(figsize=(8, 5), dpi=100, facecolor=theme.COLOR_BG)
        axes = figure.subplots(len(CHANNELS), 1, sharex=True)
        ax_dict = dict(zip(CHANNELS, axes))
        chart.render(ax_dict)
        for ax in axes:
            ax.set_facecolor(theme.COLOR_INPUT)
            ax.tick_params(colors=theme.COLOR_MUTED, labelsize=7)
            ax.yaxis.label.set_color(theme.COLOR_MUTED)
            for spine in ax.spines.values():
                spine.set_color(theme.COLOR_BORDER)
        figure.subplots_adjust(left=0.07, right=0.98, top=0.98,
                               bottom=0.05, hspace=0.25)

        canvas = FigureCanvasTkAgg(figure, master=self)
        canvas.get_tk_widget().grid(row=2, column=0, sticky="nsew",
                                    padx=10, pady=(0, 10))
        canvas.draw()

        # Record-state summary in the title bar area of the viewer.
        if session.records:
            last = session.records[-1]
            banner.configure(text=banner.cget("text") +
                             f" - last state {DeviceStateModel.state_name(last.state)}")
