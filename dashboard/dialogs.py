"""
Modal dialogs: ERASE typed-magic confirmation (FR-GS-05) and helpers for
validating the replay count entry.

file: dashboard/dialogs.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from dashboard import theme

# What the operator must type to confirm an erase (hex of the wire magic).
ERASE_CONFIRM_TEXT = "DEADC0DE"


def parse_replay_count(raw: str) -> int:
    """Validate the replay count entry; raises ValueError with a user-facing
    message when it is not a whole number in [1, 65535]."""
    try:
        count = int(raw.strip())
    except ValueError:
        raise ValueError("Enter a whole number of records to replay.") from None
    if not 1 <= count <= 65535:
        raise ValueError("Replay count must be between 1 and 65535.")
    return count


class EraseDialog(tk.Toplevel):
    """Modal confirmation: the erase only proceeds when the operator types the
    magic value. Result is True/False in .confirmed after wait_window()."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("Confirm ERASE")
        self.configure(bg=theme.COLOR_PANEL)
        self.resizable(False, False)
        self.transient(parent)
        self.confirmed = False

        body = ttk.Frame(self, padding=16, style="Panel.TFrame")
        body.grid(row=0, column=0)

        ttk.Label(body, text="This permanently erases ALL records on the device.",
                  style="Alert.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=f"Type {ERASE_CONFIRM_TEXT} to confirm:",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=2,
                                             sticky="w", pady=(10, 4))

        self._entry_var = tk.StringVar()
        entry = ttk.Entry(body, textvariable=self._entry_var, width=20)
        entry.grid(row=2, column=0, columnspan=2, sticky="ew")
        entry.focus_set()
        self._entry_var.trace_add("write", lambda *_: self._on_change())

        buttons = ttk.Frame(body, style="Panel.TFrame")
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self._erase_btn = ttk.Button(buttons, text="Erase", style="Danger.TButton",
                                     command=self._confirm, state="disabled")
        self._erase_btn.grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=1)

        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _on_change(self) -> None:
        ok = self._entry_var.get().strip().upper() == ERASE_CONFIRM_TEXT
        self._erase_btn.configure(state="normal" if ok else "disabled")

    def _confirm(self) -> None:
        if self._entry_var.get().strip().upper() != ERASE_CONFIRM_TEXT:
            return
        self.confirmed = True
        self.destroy()


def confirm_erase(parent: tk.Misc) -> bool:
    """Show the modal erase dialog; returns True only on typed confirmation."""
    dialog = EraseDialog(parent)
    parent.wait_window(dialog)
    return dialog.confirmed
