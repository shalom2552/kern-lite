"""
Rolling live chart model for the ground station. Holds the last N sensor
records plus state/reboot/gap markers, and renders all five channels onto
caller-provided matplotlib Axes with threshold lines and alert shading.

file: groundstation/chart.py
author: shalom2552
date: 2026-07-13
"""
from __future__ import annotations

from collections import deque

from .state import DeviceStateModel
from .telemetry import ALERT_MASKS, CHANNELS, SensorRecord

# Per-channel (lo, hi) threshold lines in display units, mirroring the
# firmware values in firmware/system/config.hpp.
CHANNEL_THRESHOLDS = {
    "lm35": (10.0, 40.0),
    "dht_temp": (5.0, 45.0),
    "dht_hum": (10.0, 90.0),
    "light": (0.05, 0.95),
    "pot": (0.02, 0.98),
}

_VALUE_GETTERS = {
    "lm35": lambda r: r.lm35_celsius,
    "dht_temp": lambda r: r.dht_temp_celsius,
    "dht_hum": lambda r: r.dht_humidity,
    "light": lambda r: r.light_normalized,
    "pot": lambda r: r.pot_normalized,
}

DEFAULT_CAPACITY = 120


class RollingChart:
    """Rolling window over the live record stream. The x axis is the record
    sequence number; markers older than the window are pruned on update."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self.capacity = capacity
        self.records: deque[SensorRecord] = deque(maxlen=capacity)
        self.visible: dict[str, bool] = {c: True for c in CHANNELS}

        self.state_markers: list[tuple[int, str]] = []
        self.reboot_markers: list[int] = []
        self.gap_notches: list[tuple[int, int]] = []

    def update(self, record: SensorRecord) -> None:
        """Append a record, dropping the oldest once at capacity."""
        self.records.append(record)
        self._prune_markers()

    def state_marker(self, state_change, seq: int | None = None) -> None:
        """Record a vertical marker for a state change. Accepts a
        state.Transition. `seq` pins the marker to the record-sequence x axis;
        without it the marker falls back to the transition's session_seq."""
        label = (f"{DeviceStateModel.state_name(state_change.from_state)}->"
                 f"{DeviceStateModel.state_name(state_change.to_state)}")
        x = seq if seq is not None else state_change.session_seq
        self.state_markers.append((x, label))

    def reboot_marker(self, seq: int) -> None:
        """Mark a device reboot at the given sequence number."""
        self.reboot_markers.append(seq)

    def gap_notch(self, seq: int, gap_size: int) -> None:
        """Mark a sequence gap of gap_size records ending at seq."""
        self.gap_notches.append((seq, gap_size))

    def toggle_channel(self, channel: str) -> bool:
        """Flip a channel's visibility; returns the new state."""
        self.visible[channel] = not self.visible[channel]
        return self.visible[channel]

    def channel_series(self, channel: str) -> dict:
        """Plot arrays for one channel:
        {seq, values, alert, lo, hi} with alert as per-sample booleans."""
        getter = _VALUE_GETTERS[channel]
        hi_mask, lo_mask = ALERT_MASKS[channel]
        lo, hi = CHANNEL_THRESHOLDS[channel]
        return {
            "seq": [r.seq for r in self.records],
            "values": [getter(r) for r in self.records],
            "alert": [bool(r.alert_bits & (hi_mask | lo_mask)) for r in self.records],
            "lo": lo,
            "hi": hi,
        }

    def render(self, ax_dict: dict) -> None:
        """Draw every channel in ax_dict (channel name -> matplotlib Axes).
        Hidden channels are cleared but left blank."""
        for channel, ax in ax_dict.items():
            ax.clear()
            ax.set_ylabel(channel)
            if not self.visible.get(channel, False) or not self.records:
                continue

            series = self.channel_series(channel)
            seqs = series["seq"]

            ax.plot(seqs, series["values"], color="tab:blue", linewidth=1.0)
            ax.axhline(series["lo"], color="tab:orange", linestyle="--", linewidth=0.8)
            ax.axhline(series["hi"], color="tab:red", linestyle="--", linewidth=0.8)

            if any(series["alert"]):
                # Shade the full axis height wherever the alert bit is set.
                ax.fill_between(seqs, 0, 1, where=series["alert"],
                                transform=ax.get_xaxis_transform(),
                                color="red", alpha=0.15)
            
            if seqs:
                ax.set_xlim(seqs[0], max(seqs[0] + self.capacity - 1, seqs[-1]))
            margin = (series["hi"] - series["lo"]) * 0.1
            ax.set_ylim(series["lo"] - margin, series["hi"] + margin)

            for seq, label in self.state_markers:
                ax.axvline(seq, color="tab:green", linestyle="-", linewidth=1.0)
                ax.annotate(label, xy=(seq, 1.0), xycoords=ax.get_xaxis_transform(),
                            fontsize=6, rotation=90, va="top")
            for seq in self.reboot_markers:
                ax.axvline(seq, color="black", linestyle="-", linewidth=1.5)
            for seq, gap_size in self.gap_notches:
                ax.axvline(seq, color="tab:orange", linestyle=":", linewidth=1.0)
                ax.annotate(f"gap {gap_size}", xy=(seq, 0.0),
                            xycoords=ax.get_xaxis_transform(),
                            fontsize=6, rotation=90, va="bottom")

    def _prune_markers(self) -> None:
        """Drop markers that rolled out of the window."""
        if not self.records:
            return
        oldest = self.records[0].seq
        self.state_markers = [m for m in self.state_markers if m[0] >= oldest]
        self.reboot_markers = [s for s in self.reboot_markers if s >= oldest]
        self.gap_notches = [g for g in self.gap_notches if g[0] >= oldest]
