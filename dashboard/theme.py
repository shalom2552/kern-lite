"""
Dashboard visual theme: dark palette, resolved fonts, ttk styles, and
per-channel display metadata shared by all panels.

file: dashboard/theme.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

COLOR_BG = "#0a0e17"
COLOR_PANEL = "#111825"
COLOR_PANEL_2 = "#182234"
COLOR_CARD = "#131c2b"
COLOR_BORDER = "#22304a"
COLOR_BORDER_SOFT = "#1a2740"
COLOR_TEXT = "#e6ecf5"
COLOR_MUTED = "#8595ad"
COLOR_FAINT = "#5a6b85"
COLOR_ACCENT = "#22d3ee"
COLOR_ACCENT2 = "#34d399"
COLOR_AMBER = "#fbbf24"
COLOR_RED = "#f87171"
COLOR_INPUT = "#0c1320"

FONT_FAMILY = "TkDefaultFont"
FONT_MONO_FAMILY = "TkFixedFont"

_UI_CANDIDATES = ("Inter", "SF Pro Display", "Segoe UI", "Ubuntu",
                  "Noto Sans", "DejaVu Sans", "Helvetica")
_MONO_CANDIDATES = ("JetBrains Mono", "Cascadia Code", "Fira Code",
                    "Source Code Pro", "DejaVu Sans Mono", "Consolas", "Courier")

CHANNEL_LABELS = {
    "lm35": "LM35 temperature",
    "dht_temp": "DHT temperature",
    "dht_hum": "Humidity",
    "light": "Light",
    "pot": "Potentiometer",
}

CHANNEL_UNITS = {
    "lm35": "\N{DEGREE SIGN}C",
    "dht_temp": "\N{DEGREE SIGN}C",
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

CHANNEL_COLORS = {
    "lm35": "#22d3ee",
    "dht_temp": "#60a5fa",
    "dht_hum": "#fbbf24",
    "light": "#a3e635",
    "pot": "#f472b6",
}

STATE_COLORS = {
    0: "#60a5fa",
    1: "#34d399",
    2: "#f87171",
}


def font(size: int = 10, weight: str = "normal") -> tuple:
    return (FONT_FAMILY, size, weight)


def mono(size: int = 9, weight: str = "normal") -> tuple:
    return (FONT_MONO_FAMILY, size, weight)


def format_channel_value(channel: str, value: float) -> str:
    if channel in ("light", "pot"):
        return f"{value * 100:.1f}%"
    return f"{value:.1f} {CHANNEL_UNITS[channel]}"


def _resolve_fonts(root: tk.Tk) -> None:
    global FONT_FAMILY, FONT_MONO_FAMILY
    available = set(tkfont.families(root))
    for candidate in _UI_CANDIDATES:
        if candidate in available:
            FONT_FAMILY = candidate
            break
    for candidate in _MONO_CANDIDATES:
        if candidate in available:
            FONT_MONO_FAMILY = candidate
            break


def apply_theme(root: tk.Tk) -> None:
    _resolve_fonts(root)
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=COLOR_BG)
    root.option_add("*TCombobox*Listbox.background", COLOR_INPUT)
    root.option_add("*TCombobox*Listbox.foreground", COLOR_TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", COLOR_ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", COLOR_BG)

    style.configure(".", font=font(10), background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("TFrame", background=COLOR_BG)
    style.configure("Panel.TFrame", background=COLOR_PANEL)
    style.configure("Header.TFrame", background=COLOR_PANEL)
    style.configure("Card.TFrame", background=COLOR_CARD)

    style.configure("TLabel", background=COLOR_PANEL, foreground=COLOR_TEXT)
    style.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT)
    style.configure("Muted.TLabel", background=COLOR_PANEL, foreground=COLOR_MUTED)
    style.configure("CardMuted.TLabel", background=COLOR_CARD, foreground=COLOR_MUTED)
    style.configure("Faint.TLabel", background=COLOR_PANEL, foreground=COLOR_FAINT)
    style.configure("Title.TLabel", background=COLOR_PANEL,
                    font=font(17, "bold"), foreground=COLOR_TEXT)
    style.configure("Subtitle.TLabel", background=COLOR_PANEL,
                    font=font(9), foreground=COLOR_MUTED)
    style.configure("Heading.TLabel", background=COLOR_PANEL,
                    font=font(10, "bold"), foreground=COLOR_ACCENT)
    style.configure("Metric.TLabel", background=COLOR_PANEL,
                    font=font(11, "bold"), foreground=COLOR_TEXT)
    style.configure("CardMetric.TLabel", background=COLOR_CARD,
                    font=font(11, "bold"), foreground=COLOR_TEXT)
    style.configure("Hero.TLabel", background=COLOR_CARD,
                    font=font(22, "bold"), foreground=COLOR_TEXT)
    style.configure("Alert.TLabel", background=COLOR_PANEL,
                    font=font(11, "bold"), foreground=COLOR_RED)

    style.configure("Pill.TLabel", padding=(12, 5), background=COLOR_PANEL_2,
                    foreground=COLOR_ACCENT, font=font(10, "bold"))
    style.configure("PillOk.TLabel", padding=(12, 5), background="#0f2e2a",
                    foreground=COLOR_ACCENT2, font=font(10, "bold"))
    style.configure("PillWarn.TLabel", padding=(12, 5), background="#332810",
                    foreground=COLOR_AMBER, font=font(10, "bold"))
    style.configure("PillBad.TLabel", padding=(12, 5), background="#331717",
                    foreground=COLOR_RED, font=font(10, "bold"))

    style.configure("TButton", background=COLOR_PANEL_2, foreground=COLOR_TEXT,
                    bordercolor=COLOR_BORDER, focusthickness=0, padding=(12, 7),
                    font=font(10))
    style.map("TButton",
              background=[("active", "#233250"), ("pressed", "#0e1626"),
                          ("disabled", COLOR_PANEL)],
              foreground=[("disabled", COLOR_FAINT)])
    style.configure("Accent.TButton", background=COLOR_ACCENT, foreground=COLOR_BG,
                    bordercolor=COLOR_ACCENT, padding=(12, 7), font=font(10, "bold"))
    style.map("Accent.TButton",
              background=[("active", "#3ee0f5"), ("pressed", "#12b6d4"),
                          ("disabled", COLOR_PANEL_2)],
              foreground=[("disabled", COLOR_FAINT)])
    style.configure("Danger.TButton", background="#331717", foreground=COLOR_RED,
                    bordercolor=COLOR_BORDER, padding=(12, 7), font=font(10, "bold"))
    style.map("Danger.TButton",
              background=[("active", "#4a1f1f"), ("pressed", "#200b0b"),
                          ("disabled", COLOR_PANEL)],
              foreground=[("disabled", COLOR_FAINT)])

    style.configure("TEntry", fieldbackground=COLOR_INPUT, background=COLOR_INPUT,
                    foreground=COLOR_TEXT, insertcolor=COLOR_ACCENT,
                    bordercolor=COLOR_BORDER, padding=4)
    style.configure("TCombobox", fieldbackground=COLOR_INPUT, background=COLOR_INPUT,
                    foreground=COLOR_TEXT, arrowcolor=COLOR_ACCENT,
                    bordercolor=COLOR_BORDER, padding=4)
    style.map("TCombobox",
              fieldbackground=[("readonly", COLOR_INPUT)],
              foreground=[("readonly", COLOR_TEXT)])

    style.configure("TCheckbutton", background=COLOR_PANEL, foreground=COLOR_TEXT)
    style.map("TCheckbutton",
              background=[("active", COLOR_PANEL)],
              indicatorcolor=[("selected", COLOR_ACCENT), ("!selected", COLOR_INPUT)])
    style.configure("Card.TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT)
    style.map("Card.TCheckbutton", background=[("active", COLOR_CARD)])

    style.configure("TLabelframe", background=COLOR_PANEL, foreground=COLOR_TEXT,
                    bordercolor=COLOR_BORDER_SOFT, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=COLOR_PANEL, foreground=COLOR_ACCENT,
                    font=font(10, "bold"))

    for name, color in (("Ok", COLOR_ACCENT2), ("Warn", COLOR_AMBER),
                        ("Danger", COLOR_RED), ("Accent", COLOR_ACCENT)):
        style.configure(f"{name}.Horizontal.TProgressbar", troughcolor=COLOR_INPUT,
                        background=color, bordercolor=COLOR_INPUT,
                        lightcolor=color, darkcolor=color, thickness=8)

    style.configure("Treeview", background=COLOR_INPUT, fieldbackground=COLOR_INPUT,
                    foreground=COLOR_TEXT, bordercolor=COLOR_BORDER_SOFT,
                    borderwidth=0, rowheight=24, font=font(9))
    style.configure("Treeview.Heading", background=COLOR_PANEL_2, foreground=COLOR_MUTED,
                    bordercolor=COLOR_BORDER, font=font(9, "bold"), relief="flat")
    style.map("Treeview",
              background=[("selected", COLOR_PANEL_2)],
              foreground=[("selected", COLOR_ACCENT)])
    style.map("Treeview.Heading", background=[("active", COLOR_PANEL_2)])

    style.configure("Mono.Treeview", font=mono(9), rowheight=20)

    style.configure("TNotebook", background=COLOR_BG, borderwidth=0, tabmargins=(0, 8, 0, 0))
    style.configure("TNotebook.Tab", background=COLOR_BG, foreground=COLOR_MUTED,
                    padding=(20, 9), bordercolor=COLOR_BG, font=font(10, "bold"))
    style.map("TNotebook.Tab",
              background=[("selected", COLOR_CARD)],
              foreground=[("selected", COLOR_ACCENT), ("active", COLOR_TEXT)])

    style.configure("Vertical.TScrollbar", background=COLOR_PANEL_2,
                    troughcolor=COLOR_BG, bordercolor=COLOR_BG,
                    arrowcolor=COLOR_MUTED)
