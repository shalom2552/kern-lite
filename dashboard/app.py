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

# Window widths (px) below which each part of the UI reflows.
HEADER_BREAK = 1180   # header stacks title / connection / commands vertically
LIVE_BREAK = 780      # Live tab and Timeline collapse to a single column
COMPACT_BREAK = 720   # connection, command and chart-toggle rows wrap
RESIZE_DEBOUNCE_MS = 120


def _silence_groundstation_logging() -> None:
    gs_logger = logging.getLogger("groundstation")
    gs_logger.setLevel(logging.ERROR)
    if not any(isinstance(h, logging.NullHandler) for h in gs_logger.handlers):
        gs_logger.addHandler(logging.NullHandler())


class _ScrollHost(ttk.Frame):
    """Vertical-scroll container for a notebook tab: shows a scrollbar only
    when its content is taller than the viewport, so panels are never
    clipped on small screens."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, bg=theme.COLOR_BG, highlightthickness=0,
                                bd=0, yscrollincrement=30)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical",
                                       command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.content = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.content,
                                                 anchor="nw")
        self.content.bind("<Configure>", self._sync)
        self.canvas.bind("<Configure>", self._sync)

    def _sync(self, _event=None) -> None:
        width = self.canvas.winfo_width()
        viewport_h = self.canvas.winfo_height()
        req_h = self.content.winfo_reqheight()
        height = max(req_h, viewport_h)
        self.canvas.itemconfigure(self._window, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        if req_h > viewport_h:
            self.scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.scrollbar.grid_remove()
            self.canvas.yview_moveto(0.0)


class GroundStationApp(tk.Tk):
    def __init__(self, controller: DashboardController | None = None) -> None:
        _silence_groundstation_logging()
        super().__init__()
        self.title("KERN-LITE Ground Station")
        self.minsize(560, 420)
        width = min(800, max(560, self.winfo_screenwidth() - 60))
        height = min(600, max(420, self.winfo_screenheight() - 100))
        self.geometry(f"{width}x{height}")
        self._init_width = width

        self.controller = controller if controller is not None else DashboardController()
        self._shutting_down = False
        self._after_ids: list[str] = []
        self._extra_panels: list = []
        self._records_window: tk.Toplevel | None = None
        self._layout_mode: tuple | None = None
        self._resize_after: str | None = None
        self._last_width = 0

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

        self._header = ttk.Frame(self, padding=(16, 12), style="Panel.TFrame")
        self._header.grid(row=0, column=0, sticky="ew")

        self.title_box = ttk.Frame(self._header, style="Panel.TFrame")
        ttk.Label(self.title_box, text="KERN-LITE", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(self.title_box, text="Ground Station Console",
                  style="Subtitle.TLabel").grid(row=1, column=0, sticky="w")

        self.connection = ConnectionPanel(self._header, self.controller,
                                          self._connect, self._disconnect)
        self.command_panel = CommandPanel(self._header, self.controller)

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew", padx=14, pady=(8, 14))

        live_host = _ScrollHost(notebook)
        notebook.add(live_host, text="Live")
        self._live = live_host.content

        self.channels = ChannelsPanel(self._live, self.controller)

        self._right = ttk.Frame(self._live)
        self._right.columnconfigure(0, weight=1)
        self.storage = StoragePanel(self._right, self.controller)
        self.storage.grid(row=0, column=0, sticky="new")
        self.link_panel = LinkPanel(self._right, self.controller)
        self.link_panel.grid(row=1, column=0, sticky="new", pady=(10, 0))

        self.records = RecordsPanel(self._live, self.controller,
                                    on_expand=self._expand_records)
        self.events = EventsPanel(self._live, self.controller)

        self.charts = ChartsPanel(notebook, self.controller)
        notebook.add(self.charts, text="Charts")

        timeline_host = _ScrollHost(notebook)
        notebook.add(timeline_host, text="Timeline")
        timeline_host.content.rowconfigure(0, weight=1)
        timeline_host.content.columnconfigure(0, weight=1)
        self.timeline = TimelinePanel(timeline_host.content, self.controller)
        self.timeline.grid(row=0, column=0, sticky="nsew")

        self._live_panels = (self.connection, self.command_panel, self.channels,
                             self.storage, self.link_panel, self.events,
                             self.records, self.timeline)

        self._apply_responsive(self._init_width)
        self.bind("<Configure>", self._on_root_configure)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(sequence, self._on_mousewheel, add="+")

    # -- responsive layout ---------------------------------------------------

    def _on_root_configure(self, event) -> None:
        # A bind on the root fires for every descendant; only track the
        # window itself.
        if event.widget is not self or event.width == self._last_width:
            return
        self._last_width = event.width
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(
            RESIZE_DEBOUNCE_MS, lambda: self._apply_responsive(self._last_width))

    def _apply_responsive(self, width: int) -> None:
        self._resize_after = None
        mode = (width < COMPACT_BREAK, width < HEADER_BREAK, width < LIVE_BREAK)
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        compact, header_narrow, live_narrow = mode

        self.connection.set_compact(compact)
        self.command_panel.set_compact(compact)
        self.charts.set_compact(compact)
        self.timeline.set_narrow(live_narrow)
        self._apply_header(header_narrow)
        self._apply_live(live_narrow)

    def _apply_header(self, narrow: bool) -> None:
        for widget in (self.title_box, self.connection, self.command_panel):
            widget.grid_forget()
        if narrow:
            self._header.columnconfigure(0, weight=1)
            self._header.columnconfigure(2, weight=0)
            self.title_box.grid(row=0, column=0, sticky="w")
            self.connection.grid(row=1, column=0, sticky="w", pady=(10, 0))
            self.command_panel.grid(row=2, column=0, sticky="w", pady=(8, 0))
        else:
            self._header.columnconfigure(0, weight=0)
            self._header.columnconfigure(2, weight=1)
            self.title_box.grid(row=0, column=0, sticky="w", padx=(0, 24))
            self.connection.grid(row=0, column=1, sticky="w")
            self.command_panel.grid(row=0, column=3, sticky="e")

    def _apply_live(self, narrow: bool) -> None:
        live = self._live
        for widget in (self.channels, self._right, self.records, self.events):
            widget.grid_forget()
        if narrow:
            live.columnconfigure(0, weight=1)
            live.columnconfigure(1, weight=0)
            live.rowconfigure(2, weight=0)
            live.rowconfigure(3, weight=1)
            self.channels.grid(row=0, column=0, sticky="ew")
            self._right.grid(row=1, column=0, sticky="ew", pady=(14, 0))
            self.records.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
            self.events.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        else:
            live.columnconfigure(0, weight=3)
            live.columnconfigure(1, weight=2)
            live.rowconfigure(2, weight=1)
            live.rowconfigure(3, weight=0)
            self.channels.grid(row=0, column=0, sticky="new", padx=(0, 10))
            self._right.grid(row=0, column=1, sticky="new")
            self.records.grid(row=2, column=0, sticky="nsew", padx=(0, 10),
                              pady=(14, 0))
            self.events.grid(row=2, column=1, sticky="nsew", pady=(14, 0))

    def _on_mousewheel(self, event) -> None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None and not isinstance(widget, _ScrollHost):
            if isinstance(widget, (ttk.Treeview, tk.Listbox, tk.Text)):
                return  # let the widget consume its own scrolling
            widget = widget.master
        if widget is None or not widget.scrollbar.winfo_ismapped():
            return
        up = getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0
        widget.canvas.yview_scroll(-2 if up else 2, "units")

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
        width = min(800, self.winfo_screenwidth() - 60)
        height = min(600, self.winfo_screenheight() - 100)
        window.geometry(f"{width}x{height}")
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

        if self._resize_after is not None:
            try:
                self.after_cancel(self._resize_after)
            except Exception:
                pass
            self._resize_after = None

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
        width = min(900, self.winfo_screenwidth() - 60)
        height = min(640, self.winfo_screenheight() - 100)
        self.minsize(min(560, width), min(420, height))
        self.geometry(f"{width}x{height}")
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
