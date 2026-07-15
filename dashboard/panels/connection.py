"""
Connection panel: serial port picker with refresh, connect/disconnect
buttons, and a colored link-state badge (FR-GS-01/03).

file: dashboard/panels/connection.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

try:
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - pyserial always present in practice
    list_ports = None

BADGE_STYLES = {
    "connected": "PillOk.TLabel",
    "reconnecting": "PillWarn.TLabel",
    "disconnected": "PillBad.TLabel",
}


class ConnectionPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller, on_connect, on_disconnect) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.controller = controller
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect

        self._compact: bool | None = None

        self._port_label = ttk.Label(self, text="Port")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(self, textvariable=self.port_var, width=24)
        self._refresh_btn = ttk.Button(self, text="Refresh", command=self.refresh_ports)

        self.connect_btn = ttk.Button(self, text="Connect", style="Accent.TButton",
                                      command=self._connect)
        self.disconnect_btn = ttk.Button(self, text="Disconnect", command=self._on_disconnect)

        self.badge_var = tk.StringVar(value="Disconnected")
        self.badge = ttk.Label(self, textvariable=self.badge_var, style="PillBad.TLabel")

        self.set_compact(False)
        self.refresh_ports()

    def set_compact(self, compact: bool) -> None:
        """One row on wide screens, two rows on narrow ones."""
        if compact == self._compact:
            return
        self._compact = compact
        for widget in (self._port_label, self.port_combo, self._refresh_btn,
                       self.connect_btn, self.disconnect_btn, self.badge):
            widget.grid_forget()
        if compact:
            self.port_combo.configure(width=14)
            self._port_label.grid(row=0, column=0, padx=(0, 6), sticky="w")
            self.port_combo.grid(row=0, column=1, sticky="w")
            self._refresh_btn.grid(row=0, column=2, padx=6, sticky="w")
            self.connect_btn.grid(row=1, column=0, pady=(6, 0), sticky="w")
            self.disconnect_btn.grid(row=1, column=1, pady=(6, 0), sticky="w")
            self.badge.grid(row=1, column=2, padx=6, pady=(6, 0), sticky="w")
        else:
            self.port_combo.configure(width=24)
            self._port_label.grid(row=0, column=0, padx=(0, 6))
            self.port_combo.grid(row=0, column=1)
            self._refresh_btn.grid(row=0, column=2, padx=6)
            self.connect_btn.grid(row=0, column=3, padx=(12, 4))
            self.disconnect_btn.grid(row=0, column=4, padx=4)
            self.badge.grid(row=0, column=5, padx=(12, 0))

    def refresh_ports(self) -> None:
        ports: list[str] = []
        if list_ports is not None:
            ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def _connect(self) -> None:
        self._on_connect(self.port_var.get().strip())

    def refresh(self) -> None:
        state = self.controller.link.connection_state
        self.badge_var.set(state.title())
        self.badge.configure(style=BADGE_STYLES.get(state, "StatusBad.TLabel"))
        connected = state != "disconnected"
        self.connect_btn.configure(state="disabled" if connected else "normal")
        self.disconnect_btn.configure(state="normal" if connected else "disabled")
