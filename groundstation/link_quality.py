"""
Link quality scoring and heartbeat/reboot monitoring for the ground station.

Score = 100 x (1 - weighted_error_rate), clamped to [0, 100], recomputed every
5 s over the events seen since the last evaluation. Weights: CRC 30%, sync 20%,
seq gap 25%, NACK 15%, frame timing jitter 10%. Each component rate is
normalized against a 10% fully-degraded ceiling (a 10% CRC error rate maxes
out the CRC component); jitter is normalized against the 100 ms nominal
frame interval.

file: groundstation/link_quality.py
author: shalom2552
date: 2026-07-13
"""
from __future__ import annotations

import math

DEGRADED_BELOW_PCT = 70.0
POOR_BELOW_PCT = 40.0

# error rate at which a component is considered fully degraded
FULL_DEGRADATION_RATE = 0.10
NOMINAL_FRAME_INTERVAL_S = 0.10

WEIGHT_CRC = 0.30
WEIGHT_SYNC = 0.20
WEIGHT_GAP = 0.25
WEIGHT_NACK = 0.15
WEIGHT_JITTER = 0.10


def score_from_rates(crc_rate: float, sync_rate: float, gap_rate: float,
                     nack_rate: float, jitter_s: float) -> float:
    """Pure scoring function; rates in [0, 1], jitter in seconds."""
    def component(rate: float) -> float:
        return min(1.0, max(0.0, rate) / FULL_DEGRADATION_RATE)

    weighted = (WEIGHT_CRC * component(crc_rate)
                + WEIGHT_SYNC * component(sync_rate)
                + WEIGHT_GAP * component(gap_rate)
                + WEIGHT_NACK * component(nack_rate)
                + WEIGHT_JITTER * min(1.0, max(0.0, jitter_s) / NOMINAL_FRAME_INTERVAL_S))
    return max(0.0, min(100.0, 100.0 * (1.0 - weighted)))


class LinkQualityMonitor:
    """Aggregates link events into a 0-100% quality score, watches for
    heartbeat loss (no STATUS/RECORD for 15 s while connected), and detects
    device reboots from a falling total_records counter."""

    def __init__(self, alert_log=None, interval_s: float = 5.0,
                 heartbeat_timeout_s: float = 15.0) -> None:
        self.alert_log = alert_log
        self.interval_s = interval_s
        self.heartbeat_timeout_s = heartbeat_timeout_s

        self.quality_pct = 100.0
        self.connected = True
        self.reboot_count = 0

        self._last_eval: float | None = None
        self._last_data_frame: float | None = None
        self._heartbeat_lost = False
        self._last_total_records: int | None = None
        self._reset_window()

    @property
    def degraded(self) -> bool:
        return self.quality_pct < DEGRADED_BELOW_PCT

    @property
    def poor(self) -> bool:
        return self.quality_pct < POOR_BELOW_PCT

    def on_frame(self, wall_time: float) -> None:
        """Any valid decoded frame; also resets the heartbeat timer."""
        if self._last_frame_time is not None:
            self._intervals.append(wall_time - self._last_frame_time)
        self._last_frame_time = wall_time
        self._last_data_frame = wall_time
        self._heartbeat_lost = False
        self._frames += 1

    def on_crc_error(self) -> None:
        self._crc_errors += 1

    def on_sync_error(self) -> None:
        self._sync_errors += 1

    def on_seq_gap(self, gap_size: int) -> None:
        self._gap_records += gap_size

    def on_nack(self) -> None:
        self._nacks += 1

    def on_command(self) -> None:
        self._commands += 1

    def on_status(self, total_records: int, wall_time: float,
                  seq: int | None = None) -> bool:
        """Reboot detection: total_records falling well below the previous
        value means the device restarted. Returns True when a reboot fired."""
        rebooted = (self._last_total_records is not None
                    and total_records < self._last_total_records * 0.5)
        self._last_total_records = total_records

        if rebooted:
            self.reboot_count += 1
            if self.alert_log is not None:
                self.alert_log.add("REBOOT", session_seq=seq, wall_time=wall_time,
                                   message=f"total_records dropped to {total_records}")
        return rebooted

    def update(self, wall_time: float) -> None:
        """Call periodically; recomputes the score once per interval and
        checks the heartbeat timeout."""
        if self._last_eval is None:
            self._last_eval = wall_time
        elif wall_time - self._last_eval >= self.interval_s:
            self.quality_pct = self._evaluate()
            self._reset_window()
            self._last_eval = wall_time

        if (self.connected and not self._heartbeat_lost
                and self._last_data_frame is not None
                and wall_time - self._last_data_frame >= self.heartbeat_timeout_s):
            self._heartbeat_lost = True
            if self.alert_log is not None:
                self.alert_log.add("HEARTBEAT_TIMEOUT", wall_time=wall_time,
                                   message=f"no STATUS/RECORD for {self.heartbeat_timeout_s:.0f} s")

    def _evaluate(self) -> float:
        attempts = self._frames + self._crc_errors + self._sync_errors
        if attempts == 0:
            return self.quality_pct  # no traffic this window; keep last score

        crc_rate = self._crc_errors / attempts
        sync_rate = self._sync_errors / attempts
        gap_rate = self._gap_records / (self._frames + self._gap_records)
        nack_rate = self._nacks / self._commands if self._commands else 0.0

        jitter = 0.0
        if len(self._intervals) >= 2:
            mean = sum(self._intervals) / len(self._intervals)
            var = sum((x - mean) ** 2 for x in self._intervals) / (len(self._intervals) - 1)
            jitter = math.sqrt(var)
            if jitter < 0.001:  # sub-ms is timestamp noise, not link jitter
                jitter = 0.0

        return score_from_rates(crc_rate, sync_rate, gap_rate, nack_rate, jitter)

    def _reset_window(self) -> None:
        self._frames = 0
        self._crc_errors = 0
        self._sync_errors = 0
        self._gap_records = 0
        self._nacks = 0
        self._commands = 0
        self._intervals: list[float] = []
        self._last_frame_time: float | None = None
