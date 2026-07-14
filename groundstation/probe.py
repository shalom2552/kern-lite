"""
Phase 6 blocker-gate probe: drives the board over a live serial link through
the End-of-Day 6 checklist, verifies every ground-station panel updates from
live data, records pass/fail per item, and writes a gate report.

Checks, in order:
  link       - CMD_STATUS -> STATUS decode; unknown 0xFF -> NACK BadCommand
  session    - START -> Recording, live capture, STOP -> Idle
  records    - record rate, record-level CRC, sequence continuity
  chart      - RollingChart holds all five channels; PNG render
  stats      - per-channel n/min/max/mean/stddev; lm35 mean cross-check
  timeline   - Idle -> Recording -> Idle bands; text export
  alert log  - NACK entry logged; sensor alert activity; text export
  quality    - clean-link score; heartbeat; CRC-injection reaction + recovery
  exports    - session CSV, alert log, timeline, raw frame log
  tests      - pytest test_stats.py test_timeline.py test_link_quality.py

Usage (from repo root):
    .venv/bin/python -m groundstation.probe --port /dev/ttyACM0
    .venv/bin/python -m groundstation.probe --port /dev/ttyACM0 --capture 60 --interactive --print-stream

Exit code 0 when the gate passes, 1 when any check fails, 2 when the serial
port cannot be opened.

file: groundstation/probe.py
author: shalom2552
date: 2026-07-14
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import serial

from groundstation.alert_log import AlertLog
from groundstation.chart import RollingChart
from groundstation.commands import CommandSender
from groundstation.export import (alert_log_to_text, raw_frame_log_to_text,
                                  session_to_csv, timeline_to_text)
from groundstation.frame import Frame, FrameType, NackCode, encode
from groundstation.integrity import IntegrityChecker
from groundstation.link import SerialLink
from groundstation.link_quality import LinkQualityMonitor
from groundstation.session import Session
from groundstation.state import (DeviceStateModel, STATE_FAULT, STATE_IDLE,
                                 STATE_RECORDING)
from groundstation.stats import SessionStats
from groundstation.storage_panel import StorageModel
from groundstation.telemetry import ALERT_MASKS, CHANNELS, RecordDecoder, TelemetryModel
from groundstation.timeline import StateTimeline

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"

SAMPLE_RATE_HZ = 10.0
STATUS_POLL_S = 5.0
CLEAN_QUALITY_MIN_PCT = 90.0

ANALYTICS_TESTS = (
    "tests/gs/test_stats.py",
    "tests/gs/test_timeline.py",
    "tests/gs/test_link_quality.py",
)


class GateReport:
    """Collects per-check verdicts, prints them as they land, and writes the
    final report file used as the gate evidence."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []
        self.artifacts: list[str] = []

    def add(self, status: str, name: str, detail: str = "") -> None:
        self.items.append((status, name, detail))
        line = f"[{status}] {name}"
        if detail:
            line += f" - {detail}"
        print(line)

    def artifact(self, path: str) -> None:
        self.artifacts.append(path)

    @property
    def failed(self) -> bool:
        return any(status == FAIL for status, _, _ in self.items)

    def counts(self) -> dict[str, int]:
        out = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0}
        for status, _, _ in self.items:
            out[status] += 1
        return out

    def write(self, path: str, header_lines: list[str]) -> None:
        counts = self.counts()
        verdict = "FAIL" if self.failed else "PASS"
        with open(path, "w") as f:
            f.write("KERN-LITE Phase 6 blocker-gate report\n")
            f.write("=====================================\n")
            for line in header_lines:
                f.write(line + "\n")
            f.write("\n")
            for status, name, detail in self.items:
                f.write(f"[{status}] {name}\n")
                if detail:
                    f.write(f"       {detail}\n")
            f.write("\nArtifacts\n---------\n")
            for a in self.artifacts:
                f.write(f"{a}\n")
            f.write(f"\nChecks: {counts[PASS]} pass, {counts[FAIL]} fail, "
                    f"{counts[WARN]} warn, {counts[SKIP]} skip\n")
            f.write(f"BLOCKER GATE: {verdict}\n")


class GateProbe:
    """Owns the wired link, all GS panel models, and the check sequence."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.report = GateReport()

        self.alert_log = AlertLog()
        self.state_model = DeviceStateModel()
        self.storage = StorageModel()
        self.telemetry = TelemetryModel()
        self.integrity = IntegrityChecker()
        self.session = Session()
        self.link = SerialLink(
            state_model=self.state_model,
            storage_model=self.storage,
            telemetry_model=self.telemetry,
            session=self.session,
            integrity_checker=self.integrity,
            alert_log=self.alert_log,
        )
        self.commands = CommandSender()
        self.monitor = LinkQualityMonitor(alert_log=self.alert_log)
        self.chart = RollingChart()
        self.stats = SessionStats()
        self.timeline = StateTimeline()

        self.record_count = 0
        self.record_crc_failures = 0
        self.bad_record_payloads = 0
        self.seq_gap_events = 0
        self._last_seq: int | None = None
        self._alert_state: dict[str, bool] = {c: False for c in CHANNELS}
        self._seen_transitions = 0
        self._seen_crc_errors = 0
        self._seen_sync_errors = 0
        self._printed_records = 0
        self.clean_quality_pct: float | None = None

    # ------------------------------------------------------------------ rx

    def _process_one(self) -> Frame | None:
        """Receive at most one frame and route it through every panel model
        plus the link-quality monitor. Returns the frame or None."""
        frame = self.link.receive_frame()
        now = time.time()
        self._drain_error_counters(now)
        self.monitor.update(now)

        if frame is None:
            return None

        self.session.append_raw_frame("rx", encode(frame), now)
        self.monitor.on_frame(now)

        if frame.type == FrameType.Record:
            self._on_record(frame, now)
        elif frame.type == FrameType.Status:
            rebooted = self.monitor.on_status(self.storage.total_records, now,
                                              seq=self._last_seq)
            if rebooted:
                self.timeline.on_reboot(self._last_seq or 0, now)
                self.chart.reboot_marker(self._last_seq or 0)
            self._sync_transitions()
        elif frame.type == FrameType.Nack:
            self.monitor.on_nack()
        return frame

    def _on_record(self, frame: Frame, now: float) -> None:
        # SerialLink._dispatch already ran integrity checks, telemetry ingest,
        # and the session append; this adds the Day 6 panel models on top.
        try:
            rec = RecordDecoder.decode(frame.payload)
        except ValueError:
            self.bad_record_payloads += 1
            return

        self.record_count += 1
        if not rec.record_crc_valid():
            self.record_crc_failures += 1

        if self._last_seq is not None:
            expected = (self._last_seq + 1) % 65536
            if rec.seq != expected:
                gap = (rec.seq - expected) % 65536
                self.seq_gap_events += 1
                self.monitor.on_seq_gap(gap)
                self.chart.gap_notch(rec.seq, gap)
                self.alert_log.add("SEQ_GAP", session_seq=rec.seq,
                                   wall_time=now, size=gap)
        self._last_seq = rec.seq

        self.chart.update(rec)
        self.stats.ingest(rec, now)
        self._alert_edges(rec, now)

        if self.args.print_stream or self._printed_records < 5:
            self._printed_records += 1
            print(f"  seq={rec.seq} lm35={rec.lm35_celsius:.1f}C "
                  f"dht={rec.dht_temp_celsius:.1f}C/{rec.dht_humidity:.1f}% "
                  f"light={rec.light_normalized:.3f} pot={rec.pot_normalized:.3f} "
                  f"alert=0x{rec.alert_bits:02X} fault=0x{rec.fault_bits:02X} "
                  f"crc={'ok' if rec.record_crc_valid() else 'BAD'}")

    def _alert_edges(self, rec, now: float) -> None:
        for channel, (hi_mask, lo_mask) in ALERT_MASKS.items():
            active = bool(rec.alert_bits & (hi_mask | lo_mask))
            if active == self._alert_state[channel]:
                continue
            self._alert_state[channel] = active
            category = "ALERT_ACTIVE" if active else "ALERT_CLEAR"
            self.alert_log.add(category, channel=channel,
                               session_seq=rec.seq, wall_time=now)
            self.timeline.on_alert(channel, active, rec.seq, now)

    def _sync_transitions(self) -> None:
        new = self.state_model.transitions[self._seen_transitions:]
        self._seen_transitions = len(self.state_model.transitions)
        for t in new:
            self.timeline.on_state_change(t.from_state, t.to_state,
                                          t.wall_time, len(self.session.records))
            self.chart.state_marker(t)
            self.alert_log.add(
                "STATE_TRANSITION", wall_time=t.wall_time,
                message=f"{DeviceStateModel.state_name(t.from_state)}->"
                        f"{DeviceStateModel.state_name(t.to_state)}")

    def _drain_error_counters(self, now: float) -> None:
        while self._seen_crc_errors < self.link.crc_error_count:
            self._seen_crc_errors += 1
            self.monitor.on_crc_error()
            self.alert_log.add("CRC_ERROR", wall_time=now)
        while self._seen_sync_errors < self.link.sync_error_count:
            self._seen_sync_errors += 1
            self.monitor.on_sync_error()
            self.alert_log.add("SYNC_ERROR", wall_time=now)

    def _wait_for_reply(self, timeout_s: float = 2.0,
                        expect: set[FrameType] | None = None) -> Frame | None:
        """Next frame whose type is in expect within timeout_s (default: any
        non-RECORD frame). Skipped frames — RECORD stream, heartbeat STATUS —
        keep flowing through the panels while waiting."""
        end = time.time() + timeout_s
        while time.time() < end:
            frame = self._process_one()
            if frame is None:
                time.sleep(0.01)
                continue
            if frame.type == FrameType.Record:
                continue
            if expect is not None and frame.type not in expect:
                continue
            return frame
        return None

    def _send_command(self, send_fn, *fn_args) -> None:
        send_fn(self.link, *fn_args)
        self.monitor.on_command()

    def _pump(self, duration_s: float) -> None:
        end = time.time() + duration_s
        while time.time() < end:
            if self._process_one() is None:
                time.sleep(0.005)

    # -------------------------------------------------------------- checks

    def check_status_roundtrip(self) -> bool:
        print("\n== Link: CMD_STATUS round-trip ==")
        frame = None
        for _ in range(2):
            self._send_command(self.commands.send_status)
            frame = self._wait_for_reply(2.0, expect={FrameType.Status})
            if frame is not None:
                break

        if frame is None or frame.type != FrameType.Status:
            got = "no reply" if frame is None else f"unexpected type {frame.type}"
            self.report.add(FAIL, "STATUS round-trip", got)
            return False
        if len(frame.payload) != 14:
            self.report.add(FAIL, "STATUS round-trip",
                            f"bad payload size {len(frame.payload)}")
            return False

        self.report.add(
            PASS, "STATUS round-trip",
            f"state={DeviceStateModel.state_name(self.storage.state)} "
            f"sd_mounted={self.storage.sd_mounted} "
            f"total_records={self.storage.total_records} "
            f"wrap_count={self.storage.wrap_count} "
            f"latency={self.link.last_latency_ms:.1f}ms")
        return True

    def check_nack_bad_command(self) -> None:
        print("\n== Link: unknown command 0xFF -> NACK BadCommand ==")
        frame = None
        for _ in range(2):
            self.link.record_command(0xFF)
            self.monitor.on_command()
            self.link.send_frame(Frame(0xFF, b""))
            frame = self._wait_for_reply(2.0, expect={FrameType.Nack})
            if frame is not None:
                break

        if (frame is not None and frame.type == FrameType.Nack
                and frame.payload and frame.payload[0] == NackCode.BadCommand):
            self.report.add(PASS, "NACK BadCommand on 0xFF",
                            f"code=0x{frame.payload[0]:02X}")
        elif frame is None:
            self.report.add(FAIL, "NACK BadCommand on 0xFF", "no reply")
        else:
            detail = f"unexpected reply type {frame.type}"
            if frame.type == FrameType.Nack and frame.payload:
                detail = f"unexpected NACK code 0x{frame.payload[0]:02X}"
            self.report.add(FAIL, "NACK BadCommand on 0xFF", detail)

    def ensure_idle(self) -> bool:
        if self.storage.state == STATE_FAULT:
            self.report.add(FAIL, "Device ready",
                            "device is in Fault state; clear the fault first")
            return False
        if self.storage.state == STATE_RECORDING:
            print("Device already Recording; sending CMD_STOP to normalize...")
            self._send_command(self.commands.send_stop)
            reply = self._wait_for_reply(2.0, expect={FrameType.Ack, FrameType.Nack})
            if reply is None or reply.type != FrameType.Ack:
                self.report.add(FAIL, "Device ready",
                                "could not STOP an already-recording device")
                return False
            self._send_command(self.commands.send_status)
            self._wait_for_reply(2.0, expect={FrameType.Status})
        return True

    def check_start(self) -> bool:
        print("\n== Session: CMD_START -> Recording ==")
        self._send_command(self.commands.send_start)
        reply = self._wait_for_reply(2.0, expect={FrameType.Ack, FrameType.Nack})
        if reply is None or reply.type != FrameType.Ack:
            got = "no reply" if reply is None else f"reply type {reply.type}"
            self.report.add(FAIL, "START -> ACK", got)
            return False

        self._send_command(self.commands.send_status)
        self._wait_for_reply(2.0, expect={FrameType.Status})
        if self.storage.state != STATE_RECORDING:
            self.report.add(FAIL, "START -> Recording",
                            f"STATUS still shows state={self.storage.state}")
            return False
        self.report.add(PASS, "START -> ACK, STATUS shows Recording")
        return True

    def capture(self) -> None:
        duration = self.args.capture
        print(f"\n== Capture: live stream for {duration:.0f} s ==")
        if self.args.interactive:
            print(">>> While capturing: cover the photodiode ~3 s (light alert),")
            print(">>> then turn the potentiometer to an extreme and back.")

        # Restart the quality window so pre-capture command traffic (bursty,
        # high jitter) does not pollute the clean-link score.
        self.monitor._reset_window()
        self.monitor._last_eval = None

        end = time.time() + duration
        next_status = time.time() + STATUS_POLL_S
        next_progress = time.time() + 5.0
        while time.time() < end:
            now = time.time()
            if now >= next_status:
                self._send_command(self.commands.send_status)
                next_status = now + STATUS_POLL_S
            if now >= next_progress:
                print(f"  ... {self.record_count} records, "
                      f"quality {self.monitor.quality_pct:.0f}%, "
                      f"crc_err={self.link.crc_error_count} "
                      f"gaps={self.seq_gap_events}")
                next_progress = now + 5.0
            if self._process_one() is None:
                time.sleep(0.005)

    def check_stop(self) -> None:
        print("\n== Session: CMD_STOP -> Idle ==")
        self._send_command(self.commands.send_stop)
        reply = self._wait_for_reply(2.0, expect={FrameType.Ack, FrameType.Nack})
        if reply is None or reply.type != FrameType.Ack:
            got = "no reply" if reply is None else f"reply type {reply.type}"
            self.report.add(FAIL, "STOP -> ACK", got)
            return

        self._send_command(self.commands.send_status)
        self._wait_for_reply(2.0, expect={FrameType.Status})
        if self.storage.state != STATE_IDLE:
            self.report.add(FAIL, "STOP -> Idle",
                            f"STATUS still shows state={self.storage.state}")
            return
        self.report.add(PASS, "STOP -> ACK, STATUS shows Idle")

    def check_records(self) -> None:
        print("\n== Records: rate, CRC, sequence ==")
        expected = self.args.capture * SAMPLE_RATE_HZ
        if self.record_count == 0:
            self.report.add(FAIL, "Live RECORD stream", "no records received")
            return
        if self.record_count < expected * 0.5:
            self.report.add(WARN, "Record rate",
                            f"{self.record_count} records, expected ~{expected:.0f}")
        else:
            self.report.add(PASS, "Record rate",
                            f"{self.record_count} records in {self.args.capture:.0f} s "
                            f"(~{self.record_count / self.args.capture:.1f} Hz)")

        if self.record_crc_failures or self.bad_record_payloads:
            self.report.add(FAIL, "Record CRC",
                            f"{self.record_crc_failures} CRC failures, "
                            f"{self.bad_record_payloads} undecodable payloads")
        else:
            self.report.add(PASS, "Record CRC",
                            f"all {self.record_count} records validate")

        if self.seq_gap_events:
            self.report.add(WARN, "Sequence continuity",
                            f"{self.seq_gap_events} gap event(s)")
        else:
            self.report.add(PASS, "Sequence continuity", "seq strictly monotonic")

    def check_chart(self) -> None:
        print("\n== Chart: rolling window, five channels ==")
        empty = [c for c in CHANNELS if not self.chart.channel_series(c)["values"]]
        if empty:
            self.report.add(FAIL, "Chart channels", f"no data for: {', '.join(empty)}")
            return

        bad_thresholds = [c for c in CHANNELS
                          if not (self.chart.channel_series(c)["lo"]
                                  < self.chart.channel_series(c)["hi"])]
        if bad_thresholds:
            self.report.add(FAIL, "Chart thresholds",
                            f"lo >= hi for: {', '.join(bad_thresholds)}")
        else:
            self.report.add(PASS, "Chart channels",
                            f"all 5 channels populated, window={len(self.chart.records)}"
                            f"/{self.chart.capacity}, thresholds present")

        png = os.path.join(self.session.dir, "chart.png")
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            self.report.add(SKIP, "Chart render", "matplotlib not installed")
            return
        fig, axes = plt.subplots(len(CHANNELS), 1, figsize=(10, 10), sharex=True)
        self.chart.render(dict(zip(CHANNELS, axes)))
        axes[-1].set_xlabel("seq")
        fig.savefig(png)
        plt.close(fig)
        self.report.artifact(png)
        self.report.add(PASS, "Chart render", png)

    def check_stats(self) -> None:
        print("\n== Stats: per-channel min/max/mean/stddev ==")
        print(f"  {'channel':<10} {'n':>5} {'min':>9} {'max':>9} "
              f"{'mean':>9} {'stddev':>8} {'alerts':>6} {'%alert':>7}")
        problems = []
        for name in CHANNELS:
            ch = self.stats.channels[name]
            if ch.n == 0:
                problems.append(f"{name}: no samples")
                continue
            print(f"  {name:<10} {ch.n:>5} {ch.min_val:>9.3f} {ch.max_val:>9.3f} "
                  f"{ch.mean:>9.3f} {ch.stddev:>8.3f} {ch.alert_activations:>6} "
                  f"{ch.pct_in_alert:>6.1f}%")
            if not (ch.min_val <= ch.mean <= ch.max_val):
                problems.append(f"{name}: mean outside [min, max]")

        if problems:
            self.report.add(FAIL, "Channel stats", "; ".join(problems))
        else:
            self.report.add(PASS, "Channel stats",
                            "all 5 channels: n>0, min <= mean <= max, stddev >= 0")

        # Cross-check the incremental (Welford) lm35 mean against a plain
        # sum/n over the records the TelemetryModel collected independently.
        lm35 = self.stats.channels["lm35"]
        if self.telemetry.records and lm35.n:
            naive = sum(r.lm35_celsius for r in self.telemetry.records) / len(self.telemetry.records)
            if abs(naive - lm35.mean) < 1e-6:
                self.report.add(PASS, "lm35 mean cross-check",
                                f"incremental {lm35.mean:.4f} == sum/n {naive:.4f}")
            else:
                self.report.add(FAIL, "lm35 mean cross-check",
                                f"incremental {lm35.mean:.6f} != sum/n {naive:.6f}")

    def check_timeline(self) -> None:
        print("\n== Timeline: Idle -> Recording -> Idle ==")
        pairs = {(t.from_state, t.to_state) for t in self.state_model.transitions}
        started = (STATE_IDLE, STATE_RECORDING) in pairs
        stopped = (STATE_RECORDING, STATE_IDLE) in pairs
        if not (started and stopped):
            self.report.add(FAIL, "State transitions",
                            f"observed {sorted(pairs)}; need Idle->Recording and "
                            f"Recording->Idle")
        else:
            recording_bands = [s for s in self.timeline.segments
                               if s["state"] == STATE_RECORDING and s["duration_s"]]
            detail = (f"{len(self.timeline.segments)} segment(s), closed Recording "
                      f"band of {recording_bands[0]['duration_s']:.1f} s"
                      if recording_bands else
                      f"{len(self.timeline.segments)} segment(s), no closed Recording band")
            self.report.add(PASS if recording_bands else FAIL,
                            "State timeline bands", detail)

        path = os.path.join(self.session.dir, "timeline.txt")
        timeline_to_text(self.timeline, path, now=time.time())
        self.report.artifact(path)
        if os.path.getsize(path) > 0:
            self.report.add(PASS, "Timeline export", path)
        else:
            self.report.add(FAIL, "Timeline export", "empty file")

    def check_alert_log(self) -> None:
        print("\n== Alert log ==")
        nacks = self.alert_log.filter({"NACK"})
        if nacks:
            self.report.add(PASS, "Alert log: NACK entries",
                            f"{len(nacks)} entries (first: {nacks[0].message})")
        else:
            self.report.add(FAIL, "Alert log: NACK entries",
                            "no NACK entry despite the 0xFF test")

        alerts = self.alert_log.filter({"ALERT_ACTIVE", "ALERT_CLEAR"})
        if alerts:
            self.report.add(PASS, "Alert log: sensor alerts",
                            f"{len(alerts)} activation/clear entries")
        elif self.args.interactive:
            self.report.add(FAIL, "Alert log: sensor alerts",
                            "no alert observed; was the photodiode covered?")
        else:
            self.report.add(WARN, "Alert log: sensor alerts",
                            "none observed (needs physical stimulus; "
                            "rerun with --interactive)")

        path = os.path.join(self.session.dir, "alerts.txt")
        alert_log_to_text(self.alert_log, path)
        self.report.artifact(path)
        self.report.add(PASS if os.path.getsize(path) > 0 else FAIL,
                        "Alert log export", path)

    def check_link_quality_clean(self) -> None:
        print("\n== Link quality: clean link ==")
        self.clean_quality_pct = self.monitor.quality_pct
        detail = (f"{self.clean_quality_pct:.1f}% "
                  f"(degraded={self.monitor.degraded}, poor={self.monitor.poor})")
        if self.clean_quality_pct >= CLEAN_QUALITY_MIN_PCT and not self.monitor.degraded:
            self.report.add(PASS, "Clean-link quality score", detail)
        elif self.args.capture < 3 * self.monitor.interval_s:
            self.report.add(WARN, "Clean-link quality score",
                            detail + f"; capture {self.args.capture:.0f} s is too "
                            f"short for a stable score, use >= "
                            f"{3 * self.monitor.interval_s:.0f} s")
        else:
            self.report.add(FAIL, "Clean-link quality score",
                            detail + f", expected >= {CLEAN_QUALITY_MIN_PCT:.0f}%")

        heartbeats = self.alert_log.filter({"HEARTBEAT_TIMEOUT"})
        if heartbeats:
            self.report.add(FAIL, "Heartbeat",
                            f"{len(heartbeats)} HEARTBEAT_TIMEOUT event(s)")
        else:
            self.report.add(PASS, "Heartbeat", "no timeout during the session")

    def check_crc_injection(self) -> None:
        print("\n== Link quality: CRC-error injection ==")
        # Encode a valid CMD_STATUS, flip one CRC byte, send the raw bytes.
        corrupt = bytearray(encode(Frame(FrameType.CmdStatus, b"")))
        corrupt[4] ^= 0xFF
        self.link.ser.write(bytes(corrupt))
        self.session.append_raw_frame("tx", bytes(corrupt), time.time())

        reply = self._wait_for_reply(1.5, expect={FrameType.Nack})
        nacked = (reply is not None and reply.type == FrameType.Nack
                  and reply.payload and reply.payload[0] == NackCode.CrcError)
        if nacked:
            print("  firmware replied NACK CrcError")
        else:
            print("  firmware silently dropped the corrupt frame")
            # Emulate the same event on the GS side so the score reaction is
            # still demonstrated against live traffic.
            self.monitor.on_crc_error()
            self.alert_log.add("CRC_ERROR", message="injected (synthetic GS-side)")

        # Let the monitor evaluate a window that contains the error event;
        # STATUS traffic keeps frames flowing through the window.
        self._send_command(self.commands.send_status)
        self._pump(self.monitor.interval_s + 1.5)

        degraded_score = self.monitor.quality_pct
        baseline = self.clean_quality_pct if self.clean_quality_pct is not None else 100.0
        source = "NACK CrcError" if nacked else "synthetic GS-side CRC error"
        if degraded_score < baseline:
            self.report.add(PASS, "Quality drops on CRC injection",
                            f"{baseline:.1f}% -> {degraded_score:.1f}% ({source})")
        else:
            self.report.add(FAIL, "Quality drops on CRC injection",
                            f"score stayed at {degraded_score:.1f}% ({source})")

        # Link must survive the injection: a normal STATUS round-trip works.
        self._send_command(self.commands.send_status)
        reply = self._wait_for_reply(2.0, expect={FrameType.Status})
        if reply is not None and reply.type == FrameType.Status:
            self.report.add(PASS, "Link survives injection",
                            "STATUS round-trip OK after corrupt frame")
        else:
            self.report.add(FAIL, "Link survives injection",
                            "no STATUS reply after corrupt frame")

    def check_exports(self) -> None:
        print("\n== Exports: CSV, raw frame log ==")
        csv_path = os.path.join(self.session.dir, "session.csv")
        if not self.session.records:
            self.report.add(SKIP, "Session CSV export",
                            "no records captured this run")
        else:
            session_to_csv(self.session, csv_path)
            self.report.artifact(csv_path)
            with open(csv_path) as f:
                rows = sum(1 for _ in f) - 1
            if rows == len(self.session.records):
                self.report.add(PASS, "Session CSV export",
                                f"{rows} rows == {len(self.session.records)} records")
            else:
                self.report.add(FAIL, "Session CSV export",
                                f"{rows} rows for {len(self.session.records)} records")

        frames_path = os.path.join(self.session.dir, "frames.txt")
        raw_frame_log_to_text(self.session, frames_path)
        self.report.artifact(frames_path)
        self.report.add(PASS if os.path.getsize(frames_path) > 0 else FAIL,
                        "Raw frame log export", frames_path)

    def check_analytics_tests(self) -> None:
        print("\n== Analytics tests: pytest ==")
        if self.args.skip_tests:
            self.report.add(SKIP, "Analytics tests", "--skip-tests")
            return
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *ANALYTICS_TESTS],
            cwd=repo_root, capture_output=True, text=True)
        summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        print(f"  {summary}")
        if proc.returncode == 0:
            self.report.add(PASS, "Analytics tests", summary)
        else:
            self.report.add(FAIL, "Analytics tests",
                            summary or f"pytest exited {proc.returncode}")

    # ----------------------------------------------------------------- run

    def run(self) -> int:
        session_dir = self.session.on_connect(self.args.port)
        print(f"Session directory: {session_dir}")

        try:
            print(f"Connecting to {self.args.port} @ {self.args.baud}...")
            self.link.connect(self.args.port, self.args.baud)
            self.link.ser.reset_input_buffer()
            self.link.decoder.reset()
        except serial.SerialException as e:
            print(f"Could not open port {self.args.port}: {e}")
            self.report.add(FAIL, "Serial connect", str(e))
            self._finish()
            return 2

        try:
            live_ok = self.check_status_roundtrip()
            if live_ok:
                self.check_nack_bad_command()
                if self.ensure_idle() and self.check_start():
                    self.capture()
                    self.check_stop()
                    self.check_records()
                    self.check_chart()
                    self.check_stats()
                    self.check_timeline()
                    self.check_alert_log()
                    self.check_link_quality_clean()
                    self.check_crc_injection()
        finally:
            self.link.disconnect()

        self.check_exports()
        self.check_analytics_tests()
        self._finish()
        return 1 if self.report.failed else 0

    def _finish(self) -> None:
        self.session.close()

        report_path = os.path.join(self.session.dir, "phase6_gate_report.txt")
        header = [
            f"date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"port: {self.args.port} @ {self.args.baud}",
            f"capture: {self.args.capture:.0f} s",
            f"records: {self.record_count}",
            f"link counters: tx={self.link.tx_count} rx={self.link.rx_count} "
            f"crc_err={self.link.crc_error_count} sync_err={self.link.sync_error_count} "
            f"nack={self.link.nack_count}",
            f"avg latency: {self.link.rolling_avg_latency_ms and f'{self.link.rolling_avg_latency_ms:.1f} ms' or 'n/a'}",
        ]
        self.report.write(report_path, header)

        counts = self.report.counts()
        print(f"\nReport: {report_path}")
        print(f"Checks: {counts[PASS]} pass, {counts[FAIL]} fail, "
              f"{counts[WARN]} warn, {counts[SKIP]} skip")
        if self.report.failed:
            failed = [name for status, name, _ in self.report.items if status == FAIL]
            print("PHASE 6 BLOCKER GATE: FAIL")
            for name in failed:
                print(f"  blocker: {name}")
        else:
            print("PHASE 6 BLOCKER GATE: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 6 blocker-gate probe: runs the End-of-Day 6 "
                    "checklist against a live board and records pass/fail.")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--capture", type=float, default=30.0,
                        help="seconds of live Recording capture (default 30)")
    parser.add_argument("--print-stream", action="store_true",
                        help="print every decoded record during capture "
                             "(default: only the first 5)")
    parser.add_argument("--interactive", action="store_true",
                        help="prompt for physical stimulus (photodiode/pot) so "
                             "the alert checks can pass")
    parser.add_argument("--skip-tests", action="store_true",
                        help="do not run the analytics pytest suite")
    args = parser.parse_args()

    sys.exit(GateProbe(args).run())


if __name__ == "__main__":
    main()
