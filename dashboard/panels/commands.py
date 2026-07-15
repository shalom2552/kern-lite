"""
Command panel: START / STOP / STATUS / REPLAY N / ERASE buttons, each gated
by the device state model per spec 8.6 (FR-GS-04/05).

file: dashboard/panels/commands.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from groundstation.frame import FrameType

from dashboard import dialogs


class CommandPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.controller = controller

        self.start_btn = ttk.Button(self, text="Start", command=self._start)
        self.start_btn.grid(row=0, column=0, padx=(0, 4))
        self.stop_btn = ttk.Button(self, text="Stop", command=self._stop)
        self.stop_btn.grid(row=0, column=1, padx=4)
        self.status_btn = ttk.Button(self, text="Status", command=self._status)
        self.status_btn.grid(row=0, column=2, padx=4)

        ttk.Label(self, text="Replay").grid(row=0, column=3, padx=(14, 4))
        self.replay_var = tk.StringVar(value="20")
        ttk.Entry(self, textvariable=self.replay_var, width=7).grid(row=0, column=4)
        self.replay_btn = ttk.Button(self, text="Send", command=self._replay)
        self.replay_btn.grid(row=0, column=5, padx=4)

        self.erase_btn = ttk.Button(self, text="Erase...", style="Danger.TButton",
                                    command=self._erase)
        self.erase_btn.grid(row=0, column=6, padx=(14, 0))

    def _guarded(self, action, label: str) -> None:
        try:
            action()
        except Exception as exc:
            messagebox.showerror(f"{label} failed", str(exc), parent=self)

    def _start(self) -> None:
        self._guarded(self.controller.send_start, "START")

    def _stop(self) -> None:
        self._guarded(self.controller.send_stop, "STOP")

    def _status(self) -> None:
        self._guarded(self.controller.send_status, "STATUS")

    def _replay(self) -> None:
        try:
            count = dialogs.parse_replay_count(self.replay_var.get())
        except ValueError as exc:
            messagebox.showwarning("Invalid replay count", str(exc), parent=self)
            return
        self._guarded(lambda: self.controller.send_replay(count), "REPLAY")

    def _erase(self) -> None:
        if not dialogs.confirm_erase(self.winfo_toplevel()):
            return
        self._guarded(self.controller.send_erase, "ERASE")

    def refresh(self) -> None:
        allowed = self.controller.command_allowed
        gates = {
            self.start_btn: allowed(FrameType.CmdStart),
            self.stop_btn: allowed(FrameType.CmdStop),
            self.status_btn: allowed(FrameType.CmdStatus),
            self.replay_btn: allowed(FrameType.CmdReplay),
            self.erase_btn: allowed(FrameType.CmdErase),
        }
        for button, enabled in gates.items():
            button.configure(state="normal" if enabled else "disabled")
