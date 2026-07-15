"""
Small live ground-station UI for KERN-LITE.

Run with:
  python -m groundstation.ui
"""
from __future__ import annotations

from collections import deque
import time
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - UI fallback when pyserial is missing.
    list_ports = None

from groundstation.alert_log import AlertLog
from groundstation.chart import CHANNEL_THRESHOLDS, RollingChart
from groundstation.commands import CommandSender
from groundstation.frame import FrameType
from groundstation.link import SerialLink
from groundstation.link_quality import LinkQualityMonitor
from groundstation.state import DeviceStateModel
from groundstation.stats import SessionStats
from groundstation.storage_panel import StorageModel
from groundstation.telemetry import CHANNELS, ALERT_MASKS, SensorRecord, channel_values


CHANNEL_LABELS = {
    "lm35": "LM35 temperature",
    "dht_temp": "DHT temperature",
    "dht_hum": "Humidity",
    "light": "Light",
    "pot": "Potentiometer",
}

CHANNEL_UNITS = {
    "lm35": "C",
    "dht_temp": "C",
    "dht_hum": "%",
    "light": "",
    "pot": "",
}

CHANNEL_RANGES = {
    "lm35": (-10.0, 60.0),
    "dht_temp": (-10.0, 60.0),
    "dht_hum": (0.0, 100.0),
    "light": (0.0, 1.0),
    "pot": (0.0, 1.0),
}

COLOR_BG = "#0b0f14"
COLOR_PANEL = "#121821"
COLOR_PANEL_2 = "#18212b"
COLOR_BORDER = "#263442"
COLOR_TEXT = "#e7edf3"
COLOR_MUTED = "#9aa8b6"
COLOR_ACCENT = "#3ddc97"
COLOR_AMBER = "#f0b84a"
COLOR_RED = "#f25f5c"
COLOR_INPUT = "#0f151c"

CHANNEL_COLORS = {
    "lm35": "#3ddc97",
    "dht_temp": "#5cc8ff",
    "dht_hum": "#f0b84a",
    "light": "#d0f55f",
    "pot": "#ff8bd1",
}

MAX_HISTORY_RECORDS = 500_000


class LiveTelemetry:
    """Fan-out model for SerialLink: latest record, stats, and rolling chart."""

    def __init__(self) -> None:
        self.latest: SensorRecord | None = None
        self.stats = SessionStats()
        self.chart = RollingChart()
        self.history: deque[tuple[float, SensorRecord]] = deque(maxlen=MAX_HISTORY_RECORDS)

    def ingest(self, record: SensorRecord, wall_time: float | None = None) -> None:
        wt = time.time() if wall_time is None else wall_time
        graph_time = record.timestamp + record.ms / 1000.0 if record.timestamp else wt
        self.latest = record
        self.stats.ingest(record, wt)
        self.chart.update(record)
        self.history.append((graph_time, record))


class GroundStationApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("KERN-LITE Ground Station")
        self.minsize(980, 620)

        self.alert_log = AlertLog()
        self.state_model = DeviceStateModel()
        self.storage_model = StorageModel()
        self.telemetry = LiveTelemetry()
        self.quality = LinkQualityMonitor(alert_log=self.alert_log)
        self.link = SerialLink(
            state_model=self.state_model,
            storage_model=self.storage_model,
            telemetry_model=self.telemetry,
            alert_log=self.alert_log,
        )
        self.commands = CommandSender()

        self._last_status_poll = 0.0
        self._last_quality_tick = time.time()
        self._last_crc_count = 0
        self._last_sync_count = 0
        self._last_nack_count = 0
        self._last_rendered_event_count = -1
        self.replay_count_var = tk.StringVar(value="20")
        self.graph_canvases: dict[str, tk.Canvas] = {}

        self._style()
        self._build()
        self._refresh_ports()
        self.after(50, self._poll_link)
        self.after(250, self._refresh_view)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        self.configure(bg=COLOR_BG)
        self.option_add("*TCombobox*Listbox.background", COLOR_INPUT)
        self.option_add("*TCombobox*Listbox.foreground", COLOR_TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", COLOR_PANEL_2)
        self.option_add("*TCombobox*Listbox.selectForeground", COLOR_TEXT)
        style.configure(".", font=("Segoe UI", 10), background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Panel.TFrame", background=COLOR_PANEL)
        style.configure("TLabel", background=COLOR_PANEL, foreground=COLOR_TEXT)
        style.configure("Muted.TLabel", background=COLOR_PANEL, foreground=COLOR_MUTED)
        style.configure("Title.TLabel", background=COLOR_PANEL, font=("Segoe UI", 17, "bold"), foreground=COLOR_ACCENT)
        style.configure("Metric.TLabel", background=COLOR_PANEL, font=("Segoe UI", 11, "bold"), foreground=COLOR_TEXT)
        style.configure(
            "Status.TLabel",
            padding=(10, 5),
            background=COLOR_PANEL_2,
            foreground=COLOR_ACCENT,
            relief="flat",
        )
        style.configure(
            "TButton",
            background=COLOR_PANEL_2,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            focusthickness=0,
            padding=(10, 5),
        )
        style.map(
            "TButton",
            background=[("active", "#21303d"), ("pressed", "#0e141a")],
            foreground=[("disabled", COLOR_MUTED)],
        )
        style.configure(
            "TEntry",
            fieldbackground=COLOR_INPUT,
            background=COLOR_INPUT,
            foreground=COLOR_TEXT,
            insertcolor=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLOR_INPUT,
            background=COLOR_INPUT,
            foreground=COLOR_TEXT,
            arrowcolor=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
        )
        style.map("TCombobox", fieldbackground=[("readonly", COLOR_INPUT)], foreground=[("readonly", COLOR_TEXT)])
        style.configure(
            "TLabelframe",
            background=COLOR_PANEL,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background=COLOR_PANEL,
            foreground=COLOR_ACCENT,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("Danger.Horizontal.TProgressbar", troughcolor="#30191c", background=COLOR_RED)
        style.configure("Ok.Horizontal.TProgressbar", troughcolor="#13251e", background=COLOR_ACCENT)
        style.configure("Warn.Horizontal.TProgressbar", troughcolor="#2b2615", background=COLOR_AMBER)
        style.configure(
            "Treeview",
            background=COLOR_INPUT,
            fieldbackground=COLOR_INPUT,
            foreground=COLOR_TEXT,
            bordercolor=COLOR_BORDER,
            rowheight=24,
        )
        style.configure(
            "Treeview.Heading",
            background=COLOR_PANEL_2,
            foreground=COLOR_ACCENT,
            bordercolor=COLOR_BORDER,
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Treeview", background=[("selected", COLOR_PANEL_2)], foreground=[("selected", COLOR_TEXT)])
        style.configure(
            "TNotebook",
            background=COLOR_BG,
            borderwidth=0,
            tabmargins=(0, 6, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=COLOR_PANEL_2,
            foreground=COLOR_MUTED,
            padding=(16, 8),
            bordercolor=COLOR_BORDER,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLOR_PANEL)],
            foreground=[("selected", COLOR_ACCENT)],
        )

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(14, 12, 14, 8), style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="KERN-LITE Ground Station", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.connection_text = tk.StringVar(value="Disconnected")
        ttk.Label(header, textvariable=self.connection_text, style="Status.TLabel").grid(row=0, column=2, sticky="e")

        controls = ttk.Frame(header, style="Panel.TFrame")
        controls.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Port").grid(row=0, column=0, padx=(0, 6))
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(controls, textvariable=self.port_var, width=22)
        self.port_combo.grid(row=0, column=1, sticky="w")
        ttk.Button(controls, text="Refresh", command=self._refresh_ports).grid(row=0, column=2, padx=6)
        ttk.Button(controls, text="Connect", command=self._connect).grid(row=0, column=3, padx=(14, 4))
        ttk.Button(controls, text="Disconnect", command=self._disconnect).grid(row=0, column=4, padx=4)
        ttk.Button(controls, text="Start", command=self._send_start).grid(row=0, column=5, padx=(14, 4))
        ttk.Button(controls, text="Stop", command=self._send_stop).grid(row=0, column=6, padx=4)
        ttk.Button(controls, text="Status", command=self._send_status).grid(row=0, column=7, padx=4)
        ttk.Label(controls, text="Replay").grid(row=0, column=8, padx=(14, 4))
        replay_entry = ttk.Entry(controls, textvariable=self.replay_count_var, width=6)
        replay_entry.grid(row=0, column=9, padx=4)
        ttk.Button(controls, text="Send", command=self._send_replay_from_input).grid(row=0, column=10, padx=4)

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew", padx=14, pady=(8, 14))

        body = ttk.Frame(notebook, padding=(0, 0, 0, 0))
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        notebook.add(body, text="Current sensors")

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(5, weight=1)

        self.channel_rows: dict[str, dict[str, object]] = {}
        for row, channel in enumerate(CHANNELS):
            self._build_channel_row(left, row, channel)
        self._build_record_table(left, 5)

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        self.device_vars = {
            "state": tk.StringVar(value="-"),
            "sd": tk.StringVar(value="-"),
            "total": tk.StringVar(value="0"),
            "file": tk.StringVar(value="-"),
            "live": tk.StringVar(value="0"),
            "quality": tk.StringVar(value="100%"),
            "traffic": tk.StringVar(value="rx 0 / tx 0"),
            "errors": tk.StringVar(value="crc 0 / sync 0 / nack 0"),
            "latency": tk.StringVar(value="-"),
            "seq": tk.StringVar(value="-"),
        }
        self._build_info_panel(right)

        log_frame = ttk.LabelFrame(right, text="Events", padding=10)
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.event_list = tk.Listbox(
            log_frame,
            height=9,
            activestyle="none",
            bg=COLOR_INPUT,
            fg=COLOR_TEXT,
            selectbackground=COLOR_PANEL_2,
            selectforeground=COLOR_TEXT,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            relief="flat",
            borderwidth=0,
        )
        self.event_list.grid(row=0, column=0, sticky="nsew")

        print_frame = ttk.LabelFrame(right, text="Record printout", padding=10)
        print_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        print_frame.rowconfigure(0, weight=1)
        print_frame.columnconfigure(0, weight=1)
        self.record_printout = tk.Listbox(
            print_frame,
            height=9,
            activestyle="none",
            bg=COLOR_INPUT,
            fg=COLOR_TEXT,
            selectbackground=COLOR_PANEL_2,
            selectforeground=COLOR_TEXT,
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            relief="flat",
            borderwidth=0,
            font=("Consolas", 9),
        )
        self.record_printout.grid(row=0, column=0, sticky="nsew")

        graphs = ttk.Frame(notebook, padding=(0, 0, 0, 0))
        graphs.columnconfigure(0, weight=1)
        for row in range(len(CHANNELS)):
            graphs.rowconfigure(row, weight=1)
        notebook.add(graphs, text="Graphs")
        self._build_graphs_tab(graphs)

    def _build_graphs_tab(self, parent: ttk.Frame) -> None:
        for row, channel in enumerate(CHANNELS):
            frame = ttk.LabelFrame(parent, text=CHANNEL_LABELS[channel], padding=8)
            frame.grid(row=row, column=0, sticky="nsew", pady=(0, 8))
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)

            canvas = tk.Canvas(
                frame,
                height=112,
                bg=COLOR_INPUT,
                highlightthickness=1,
                highlightbackground=COLOR_BORDER,
                bd=0,
            )
            canvas.grid(row=0, column=0, sticky="nsew")
            self.graph_canvases[channel] = canvas

    def _build_record_table(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Recent records", padding=10)
        frame.grid(row=row, column=0, sticky="nsew", pady=(0, 10))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        columns = ("source", "seq", "lm35", "dht_temp", "hum", "light", "pot", "alerts")
        self.record_table = ttk.Treeview(frame, columns=columns, show="headings", height=8)
        headings = {
            "source": "source",
            "seq": "seq",
            "lm35": "LM35 C",
            "dht_temp": "DHT C",
            "hum": "hum %",
            "light": "light %",
            "pot": "pot %",
            "alerts": "alerts",
        }
        widths = {
            "source": 70,
            "seq": 70,
            "lm35": 85,
            "dht_temp": 85,
            "hum": 80,
            "light": 80,
            "pot": 80,
            "alerts": 80,
        }
        for column in columns:
            self.record_table.heading(column, text=headings[column])
            self.record_table.column(column, width=widths[column], anchor="center", stretch=True)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.record_table.yview)
        self.record_table.configure(yscrollcommand=scrollbar.set)
        self.record_table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def _build_channel_row(self, parent: ttk.Frame, row: int, channel: str) -> None:
        frame = ttk.LabelFrame(parent, text=CHANNEL_LABELS[channel], padding=10)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(1, weight=1)

        value_var = tk.StringVar(value="-")
        stats_var = tk.StringVar(value="min - / mean - / max -")
        ttk.Label(frame, textvariable=value_var, style="Metric.TLabel", width=13).grid(row=0, column=0, sticky="w")

        progress = ttk.Progressbar(frame, maximum=100.0, style="Ok.Horizontal.TProgressbar")
        progress.grid(row=0, column=1, sticky="ew", padx=10)

        alert_var = tk.StringVar(value="normal")
        ttk.Label(frame, textvariable=alert_var, width=9).grid(row=0, column=2, sticky="e")
        ttk.Label(frame, textvariable=stats_var).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        lo, hi = CHANNEL_THRESHOLDS[channel]
        ttk.Label(frame, text=f"thresholds {lo:g} to {hi:g}").grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 0))

        self.channel_rows[channel] = {
            "value": value_var,
            "stats": stats_var,
            "alert": alert_var,
            "progress": progress,
        }

    def _build_info_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Board status", padding=10)
        panel.grid(row=0, column=0, sticky="new")
        panel.columnconfigure(1, weight=1)

        labels = [
            ("Device state", "state"),
            ("SD mounted", "sd"),
            ("Total records", "total"),
            ("Current file", "file"),
            ("Live records", "live"),
            ("Last sequence", "seq"),
            ("Link quality", "quality"),
            ("Traffic", "traffic"),
            ("Errors", "errors"),
            ("Latency", "latency"),
        ]
        for row, (label, key) in enumerate(labels):
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Label(panel, textvariable=self.device_vars[key], style="Metric.TLabel").grid(
                row=row, column=1, sticky="e", pady=2
            )

    def _refresh_ports(self) -> None:
        ports = []
        if list_ports is not None:
            ports = [port.device for port in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def _connect(self) -> None:
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("No port", "Choose a serial port first.")
            return
        try:
            self.link.connect(port)
            self.alert_log.add("GS_EVENT", message=f"connected to {port}")
            self._send_status()
        except Exception as exc:
            messagebox.showerror("Connect failed", str(exc))

    def _disconnect(self) -> None:
        self.link.disconnect()
        self.alert_log.add("GS_EVENT", message="disconnected")

    def _send_start(self) -> None:
        self._send_command(lambda: self.commands.send_start(self.link), "START")

    def _send_stop(self) -> None:
        self._send_command(lambda: self.commands.send_stop(self.link), "STOP")

    def _send_status(self) -> None:
        self._send_command(lambda: self.commands.send_status(self.link), "STATUS")

    def _send_replay_from_input(self) -> None:
        try:
            count = int(self.replay_count_var.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid replay count", "Enter a whole number of records to replay.")
            return

        if count <= 0 or count > 65535:
            messagebox.showwarning("Invalid replay count", "Replay count must be between 1 and 65535.")
            return

        self._send_replay(count)

    def _send_replay(self, count: int) -> None:
        self._send_command(lambda: self.commands.send_replay(self.link, count), f"REPLAY {count}")

    def _send_command(self, action, label: str) -> None:
        try:
            action()
            self.quality.on_command()
            self.alert_log.add("GS_EVENT", message=f"sent {label}")
        except Exception as exc:
            messagebox.showerror(f"{label} failed", str(exc))

    def _poll_link(self) -> None:
        now = time.time()
        if self.link.connection_state == "connected":
            while True:
                frame = self.link.receive_frame()
                if frame is None:
                    break
                self.quality.on_frame(now)
                if frame.type == FrameType.Status:
                    self.quality.on_status(self.storage_model.total_records, now)
                elif frame.type == FrameType.Record:
                    source = "replay" if self.link._in_replay else "live"
                    self._append_record_row(source)
                elif frame.type == FrameType.Nack:
                    self.quality.on_nack()

            if now - self._last_status_poll >= 5.0:
                self._last_status_poll = now
                try:
                    self.commands.send_status(self.link)
                    self.quality.on_command()
                except Exception:
                    pass

        self._feed_error_deltas()
        self.quality.update(now)
        self.after(50, self._poll_link)

    def _feed_error_deltas(self) -> None:
        for _ in range(self.link.crc_error_count - self._last_crc_count):
            self.quality.on_crc_error()
        for _ in range(self.link.sync_error_count - self._last_sync_count):
            self.quality.on_sync_error()
        for _ in range(self.link.nack_count - self._last_nack_count):
            self.quality.on_nack()
        self._last_crc_count = self.link.crc_error_count
        self._last_sync_count = self.link.sync_error_count
        self._last_nack_count = self.link.nack_count

    def _refresh_view(self) -> None:
        self.connection_text.set(self.link.connection_state.title())
        self._refresh_status()
        self._refresh_channels()
        self._refresh_graphs()
        self._refresh_events()
        self.after(250, self._refresh_view)

    def _refresh_status(self) -> None:
        state_name = self.state_model.state_name(self.state_model.state)
        self.device_vars["state"].set(state_name)
        self.device_vars["sd"].set("yes" if self.storage_model.sd_mounted else "no")
        self.device_vars["total"].set(str(self.storage_model.total_records))
        self.device_vars["file"].set(f"{self.storage_model.current_file} / {self.storage_model.file_count or 4}")
        self.device_vars["live"].set(str(self.storage_model.live_record_count))
        self.device_vars["quality"].set(f"{self.quality.quality_pct:.0f}%")
        self.device_vars["traffic"].set(f"rx {self.link.rx_count} / tx {self.link.tx_count}")
        self.device_vars["errors"].set(
            f"crc {self.link.crc_error_count} / sync {self.link.sync_error_count} / nack {self.link.nack_count}"
        )
        latency = self.link.last_latency_ms
        self.device_vars["latency"].set("-" if latency is None else f"{latency:.0f} ms")
        latest = self.telemetry.latest
        self.device_vars["seq"].set("-" if latest is None else str(latest.seq))

    def _refresh_channels(self) -> None:
        latest = self.telemetry.latest
        values = channel_values(latest) if latest is not None else {}
        for channel in CHANNELS:
            row = self.channel_rows[channel]
            progress: ttk.Progressbar = row["progress"]  # type: ignore[assignment]
            value_var: tk.StringVar = row["value"]  # type: ignore[assignment]
            stats_var: tk.StringVar = row["stats"]  # type: ignore[assignment]
            alert_var: tk.StringVar = row["alert"]  # type: ignore[assignment]

            value = values.get(channel)
            if value is None:
                value_var.set("-")
                progress["value"] = 0.0
                alert_var.set("normal")
            else:
                value_var.set(self._format_channel_value(channel, value))
                progress["value"] = self._scale_channel(channel, value)
                alert = self._channel_alert(latest, channel)
                alert_var.set("alert" if alert else "normal")
                progress.configure(style="Danger.Horizontal.TProgressbar" if alert else "Ok.Horizontal.TProgressbar")

            stats = self.telemetry.stats.channels[channel]
            if stats.n:
                stats_var.set(
                    f"min {stats.min_val:.2f} / mean {stats.mean:.2f} / max {stats.max_val:.2f}"
                )
            else:
                stats_var.set("min - / mean - / max -")

    def _refresh_events(self) -> None:
        entries = self.alert_log.entries[-9:]
        if self._last_rendered_event_count == len(self.alert_log.entries):
            return
        self._last_rendered_event_count = len(self.alert_log.entries)
        self.event_list.delete(0, tk.END)
        for entry in entries:
            stamp = time.strftime("%H:%M:%S", time.localtime(entry.wall_time))
            self.event_list.insert(tk.END, f"{stamp} {entry.category} {entry.message}")

    def _append_record_row(self, source: str) -> None:
        record = self.telemetry.latest
        if record is None:
            return

        values = channel_values(record)
        self._append_record_printout(source, record, values)
        self.record_table.insert(
            "",
            0,
            values=(
                source,
                record.seq,
                f"{values['lm35']:.1f}",
                f"{values['dht_temp']:.1f}",
                f"{values['dht_hum']:.1f}",
                f"{values['light'] * 100:.1f}",
                f"{values['pot'] * 100:.1f}",
                f"0x{record.alert_bits:02X}",
            ),
        )

        rows = self.record_table.get_children()
        for item in rows[200:]:
            self.record_table.delete(item)

    def _append_record_printout(self, source: str, record: SensorRecord, values: dict[str, float]) -> None:
        line = (
            f"{source:<6} seq={record.seq:<5} "
            f"lm35={values['lm35']:>5.1f}C "
            f"dht={values['dht_temp']:>5.1f}C "
            f"hum={values['dht_hum']:>5.1f}% "
            f"light={values['light'] * 100:>5.1f}% "
            f"pot={values['pot'] * 100:>5.1f}% "
            f"alerts=0x{record.alert_bits:02X}"
        )
        self.record_printout.insert(0, line)
        while self.record_printout.size() > 200:
            self.record_printout.delete(tk.END)

    def _refresh_graphs(self) -> None:
        samples = self._graph_samples()
        for channel, canvas in self.graph_canvases.items():
            self._draw_channel_graph(canvas, channel, samples)

    def _graph_samples(self) -> list[tuple[float, SensorRecord]]:
        return sorted(self.telemetry.history, key=lambda sample: sample[0])

    def _draw_channel_graph(self, canvas: tk.Canvas, channel: str, samples: list[tuple[float, SensorRecord]]) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        pad_left = 44
        pad_right = 12
        pad_top = 12
        pad_bottom = 24
        plot_w = max(width - pad_left - pad_right, 1)
        plot_h = max(height - pad_top - pad_bottom, 1)

        canvas.create_rectangle(pad_left, pad_top, width - pad_right, height - pad_bottom, outline=COLOR_BORDER)
        for i in range(1, 4):
            y = pad_top + plot_h * i / 4
            canvas.create_line(pad_left, y, width - pad_right, y, fill="#1d2a35")

        lo, hi = CHANNEL_RANGES[channel]
        threshold_lo, threshold_hi = CHANNEL_THRESHOLDS[channel]
        for threshold, color in ((threshold_lo, COLOR_AMBER), (threshold_hi, COLOR_RED)):
            if lo <= threshold <= hi:
                y = pad_top + (hi - threshold) / (hi - lo) * plot_h
                canvas.create_line(pad_left, y, width - pad_right, y, fill=color, dash=(4, 3))

        canvas.create_text(8, pad_top, text=f"{hi:g}", fill=COLOR_MUTED, anchor="nw", font=("Segoe UI", 8))
        canvas.create_text(8, height - pad_bottom - 12, text=f"{lo:g}", fill=COLOR_MUTED, anchor="nw", font=("Segoe UI", 8))

        if not samples:
            canvas.create_text(
                width / 2,
                height / 2,
                text="waiting for records",
                fill=COLOR_MUTED,
                font=("Segoe UI", 10),
            )
            return

        samples = self._downsample_graph_samples(samples, max_points=max(int(plot_w), 1))
        times = [sample_time for sample_time, _record in samples]
        records = [record for _sample_time, record in samples]
        values = [channel_values(record)[channel] for record in records]
        first_time = times[0]
        last_time = times[-1]
        span = max(last_time - first_time, 1e-6)
        points = []
        for sample_time, value in zip(times, values):
            x = pad_left + ((sample_time - first_time) / span) * plot_w
            scaled = max(lo, min(hi, value))
            y = pad_top + (hi - scaled) / (hi - lo) * plot_h
            points.extend((x, y))

        if len(points) >= 4:
            canvas.create_line(*points, fill=CHANNEL_COLORS[channel], width=2, smooth=True)
        else:
            canvas.create_oval(points[0] - 2, points[1] - 2, points[0] + 2, points[1] + 2, fill=CHANNEL_COLORS[channel])

        latest = values[-1]
        latest_text = self._format_channel_value(channel, latest)
        first_seq = records[0].seq
        last_seq = records[-1].seq
        canvas.create_text(
            pad_left,
            height - 8,
            text=f"seq {first_seq} -> {last_seq} | {len(samples)} pts",
            fill=COLOR_MUTED,
            anchor="sw",
            font=("Segoe UI", 8),
        )
        canvas.create_text(
            width - pad_right,
            pad_top + 2,
            text=latest_text,
            fill=CHANNEL_COLORS[channel],
            anchor="ne",
            font=("Segoe UI", 10, "bold"),
        )

    def _downsample_graph_samples(
        self,
        samples: list[tuple[float, SensorRecord]],
        max_points: int,
    ) -> list[tuple[float, SensorRecord]]:
        if len(samples) <= max_points * 2:
            return samples

        step = max(len(samples) // max_points, 1)
        downsampled = samples[::step]
        if downsampled[-1] is not samples[-1]:
            downsampled.append(samples[-1])
        return downsampled

    def _channel_alert(self, record: SensorRecord | None, channel: str) -> bool:
        if record is None:
            return False
        hi_mask, lo_mask = ALERT_MASKS[channel]
        return bool(record.alert_bits & (hi_mask | lo_mask))

    def _scale_channel(self, channel: str, value: float) -> float:
        lo, hi = CHANNEL_RANGES[channel]
        if hi <= lo:
            return 0.0
        return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100.0))

    def _format_channel_value(self, channel: str, value: float) -> str:
        unit = CHANNEL_UNITS[channel]
        if channel in ("light", "pot"):
            return f"{value * 100:.1f}%"
        return f"{value:.1f} {unit}"

    def destroy(self) -> None:
        self.link.disconnect()
        super().destroy()


def main() -> None:
    app = GroundStationApp()
    app.mainloop()


if __name__ == "__main__":
    main()
