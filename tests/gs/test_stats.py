"""
Analytics tests for groundstation.stats.ChannelStats.

file: tests/gs/test_stats.py
author: Smallejoo
date: 2026-14-07
"""
from __future__ import annotations
import inspect
import math
import pytest

from groundstation.stats import ChannelStats


def _sample_stddev(values: list[float]) -> float:
    try:
        import numpy as np

        return float(np.std(values, ddof=1))
    except ModuleNotFoundError:
        mean = sum(values) / len(values)
        return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _stat_value(value):
    if isinstance(value, tuple):
        return value[0]
    if hasattr(value, "value"):
        return value.value
    return value


def _update(stats: ChannelStats, value: float, *, seq: int, wall_time: float, alert: bool = False) -> None:
    signature = inspect.signature(stats.update)
    kwargs = {}
    for name in signature.parameters:
        if name in ("value", "sample"):
            kwargs[name] = value
        elif name in ("seq", "session_seq"):
            kwargs[name] = seq
        elif name in ("wall_time", "timestamp", "t"):
            kwargs[name] = wall_time
        elif name in ("alert", "alert_active", "active"):
            kwargs[name] = alert

    if kwargs:
        stats.update(**kwargs)
    else:
        stats.update(value, seq, wall_time, alert)


def test_channel_stats_incremental_mean_stddev_min_max():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    stats = ChannelStats()

    for seq, value in enumerate(values):
        _update(stats, value, seq=seq, wall_time=float(seq))

    assert stats.n == 5
    assert stats.mean == pytest.approx(30.0)
    assert stats.stddev == pytest.approx(15.81, abs=0.01)
    assert stats.stddev == pytest.approx(_sample_stddev(values), abs=1e-6)
    assert _stat_value(stats.min_val) == pytest.approx(10.0)
    assert _stat_value(stats.max_val) == pytest.approx(50.0)


def test_channel_stats_alert_timing_counts_previous_active_interval():
    stats = ChannelStats()

    for seq, wall_time in enumerate([0.0, 1.0, 2.0, 3.0, 4.0]):
        _update(stats, 25.0, seq=seq, wall_time=wall_time, alert=wall_time in (1.0, 2.0, 3.0))

    assert stats.alert_activations == 1
    assert stats.time_in_alert_s == pytest.approx(2.0)

