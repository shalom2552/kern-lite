"""
Per-channel incremental statistics for the ground station: min/max (with seq),
mean and stddev via Welford's online algorithm, and alert activation/duration
tracking. No recomputation over past records.

file: groundstation/stats.py
author: shalom2552
date: 2026-07-13
"""
from __future__ import annotations

import math

from .telemetry import ALERT_MASKS, CHANNELS, SensorRecord, channel_values


class ChannelStats:
    """Running statistics for one sensor channel."""

    def __init__(self) -> None:
        self.n = 0
        self.min_val: float | None = None
        self.min_seq: int | None = None
        self.max_val: float | None = None
        self.max_seq: int | None = None
        self.mean = 0.0
        self.m2 = 0.0

        self.alert_active = False
        self.alert_activations = 0
        self.time_in_alert_s = 0.0

        self._first_ts: float | None = None
        self._last_ts: float | None = None

    def update(self, value: float, alert: bool = False,
               wall_time: float | None = None, seq: int | None = None) -> None:
        self.n += 1

        if self.min_val is None or value < self.min_val:
            self.min_val = value
            self.min_seq = seq
        if self.max_val is None or value > self.max_val:
            self.max_val = value
            self.max_seq = seq

        # Welford's online mean/variance
        delta = value - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (value - self.mean)

        if alert and not self.alert_active:
            self.alert_activations += 1

        # Count an interval as alert time only when both of its endpoints
        # are in alert, so an activation at t1 cleared at t3 yields t3-t1.
        if alert and self.alert_active and wall_time is not None and self._last_ts is not None:
            self.time_in_alert_s += max(0.0, wall_time - self._last_ts)

        self.alert_active = alert
        if wall_time is not None:
            if self._first_ts is None:
                self._first_ts = wall_time
            self._last_ts = wall_time

    @property
    def stddev(self) -> float:
        """Sample standard deviation, sqrt(M2 / (n-1)); 0.0 until n >= 2."""
        if self.n < 2:
            return 0.0
        return math.sqrt(self.m2 / (self.n - 1))

    @property
    def session_duration_s(self) -> float:
        if self._first_ts is None or self._last_ts is None:
            return 0.0
        return self._last_ts - self._first_ts

    @property
    def pct_in_alert(self) -> float:
        duration = self.session_duration_s
        if duration <= 0.0:
            return 0.0
        return self.time_in_alert_s / duration * 100.0


class SessionStats:
    """ChannelStats for all five channels, fed from decoded records."""

    def __init__(self) -> None:
        self.channels: dict[str, ChannelStats] = {c: ChannelStats() for c in CHANNELS}

    def ingest(self, record: SensorRecord, wall_time: float) -> None:
        for name, value in channel_values(record).items():
            hi_mask, lo_mask = ALERT_MASKS[name]
            alert = bool(record.alert_bits & (hi_mask | lo_mask))
            self.channels[name].update(value, alert=alert, wall_time=wall_time, seq=record.seq)
