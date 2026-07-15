"""
Events panel: timestamped alert/event history from AlertLog with per-category
filter checkboxes (FR-GS-12).

file: dashboard/panels/events.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from groundstation.alert_log import CATEGORIES

MAX_ROWS = 500


class EventsPanel(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc, controller) -> None:
        super().__init__(parent, text="Events", padding=8)
        self.controller = controller
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        filters = ttk.Frame(self, style="Panel.TFrame")
        filters.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.filter_vars: dict[str, tk.BooleanVar] = {}
        for i, category in enumerate(CATEGORIES):
            var = tk.BooleanVar(value=True)
            self.filter_vars[category] = var
            ttk.Checkbutton(filters, text=category, variable=var,
                            command=self._repopulate).grid(
                row=i // 5, column=i % 5, sticky="w", padx=(0, 10))

        columns = ("time", "category", "seq", "message")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=8)
        widths = {"time": 80, "category": 150, "seq": 60, "message": 420}
        for column in columns:
            self.tree.heading(column, text=column)
            self.tree.column(column, width=widths[column],
                             anchor="w", stretch=(column == "message"))
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        self._rendered = 0

    def _wanted(self) -> set[str]:
        return {c for c, var in self.filter_vars.items() if var.get()}

    def _insert(self, entry) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(entry.wall_time))
        seq = "-" if entry.session_seq is None else str(entry.session_seq)
        self.tree.insert("", 0, values=(stamp, entry.category, seq, entry.message))

    def _trim(self) -> None:
        rows = self.tree.get_children()
        for item in rows[MAX_ROWS:]:
            self.tree.delete(item)

    def _repopulate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        wanted = self._wanted()
        for entry in self.controller.alert_log.entries:
            if entry.category in wanted:
                self._insert(entry)
        self._trim()
        self._rendered = len(self.controller.alert_log.entries)

    def refresh(self) -> None:
        entries = self.controller.alert_log.entries
        if len(entries) == self._rendered:
            return
        wanted = self._wanted()
        for entry in entries[self._rendered:]:
            if entry.category in wanted:
                self._insert(entry)
        self._rendered = len(entries)
        self._trim()
