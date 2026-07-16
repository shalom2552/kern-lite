"""
Headless dashboard controller: owns and wires every groundstation model,
pumps decoded frames out of the serial link, and fans derived events
(sequence gaps, state transitions, channel alerts, reboots, link errors)
into the chart, timeline, alert log, and link-quality monitor.

No tkinter imports here -- the UI layer only reads controller state on a
refresh tick and calls controller methods from button handlers.

file: dashboard/controller.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import time
from collections import deque

from groundstation.alert_log import AlertLog
from groundstation.chart import RollingChart
from groundstation.commands import CommandSender
from groundstation.frame import Frame, FrameType, encode
from groundstation.integrity import IntegrityChecker
from groundstation.link import SerialLink
from groundstation.link_quality import LinkQualityMonitor
from groundstation.session import Session
from groundstation.state import DeviceStateModel
from groundstation.stats import SessionStats
from groundstation.storage_panel import StorageModel
from groundstation.telemetry import CHANNELS, SensorRecord
from groundstation.timeline import StateTimeline

# Mirrors firmware/system/config.hpp kEraseMagic.
ERASE_MAGIC = 0xDEADC0DE

STATUS_POLL_INTERVAL_S = 5.0
RECORD_HISTORY = 2000


class RecordRow:
    __slots__ = ("wall_time", "record", "source")

    def __init__(self, wall_time: float, record: SensorRecord, source: str) -> None:
        self.wall_time = wall_time
        self.record = record
        self.source = source


class TelemetryFanout:
    """Receives decoded records from SerialLink._dispatch and fans them out to
    the stats and rolling chart, tracking sequence gaps along the way."""

    def __init__(self, stats: SessionStats, chart: RollingChart,
                 quality: LinkQualityMonitor, alert_log: AlertLog,
                 integrity: IntegrityChecker) -> None:
        self.stats = stats
        self.chart = chart
        self.quality = quality
        self.alert_log = alert_log
        self.integrity = integrity

        self.latest: SensorRecord | None = None
        self.record_count = 0
        self.history: deque[RecordRow] = deque(maxlen=RECORD_HISTORY)
        self._last_seq: int | None = None
        self._last_uptime_ms: int | None = None
        self.link: SerialLink | None = None

    def ingest(self, record: SensorRecord, wall_time: float | None = None) -> None:
        wt = time.time() if wall_time is None else wall_time

        in_replay = self.link is not None and self.link._in_replay
        if not in_replay:
            uptime_ms = record.timestamp * 1000 + record.ms
            if self._last_uptime_ms is not None and uptime_ms < self._last_uptime_ms:
                # device uptime went backwards: reboot, seq counter reset
                self.quality.on_seq_reset(record.seq, wt)
            else:
                gap = self.integrity.check_sequence(record, self._last_seq)
                if gap:
                    self.chart.gap_notch(record.seq, gap)
                    self.quality.on_seq_gap(gap)
                    self.alert_log.add("SEQ_GAP", session_seq=record.seq, wall_time=wt,
                                       message=f"missing {gap} record(s)")
            self._last_uptime_ms = uptime_ms
            self._last_seq = record.seq

        self.latest = record
        self.record_count += 1
        self.history.append(RecordRow(wt, record, "replay" if in_replay else "live"))
        self.stats.ingest(record, wt)
        self.chart.update(record)


class LoggedLink(SerialLink):
    """SerialLink that also appends raw TX/RX frame bytes to the session's
    frames.log. RX bytes are recovered by re-encoding the decoded frame,
    which is exact because the codec is deterministic."""

    def send_frame(self, frame: Frame) -> None:
        super().send_frame(frame)
        self._log_raw("TX", frame)

    def receive_frame(self) -> Frame | None:
        frame = super().receive_frame()
        if frame is not None:
            self._log_raw("RX", frame)
        return frame

    def _log_raw(self, direction: str, frame: Frame) -> None:
        if self.session is None:
            return
        try:
            self.session.append_raw_frame(direction, encode(frame), time.time())
        except RuntimeError:
            pass  # session not open (e.g. frames drained during shutdown)


class DashboardController:
    """Everything the dashboard shows or does, minus the widgets."""

    def __init__(self, session_base_dir: str = "sessions") -> None:
        self.alert_log = AlertLog()
        self.state_model = DeviceStateModel()
        self.storage_model = StorageModel()
        self.session = Session(base_dir=session_base_dir)
        self.integrity = IntegrityChecker()
        self.quality = LinkQualityMonitor(alert_log=self.alert_log)
        self.timeline = StateTimeline()
        self.stats = SessionStats()
        self.chart = RollingChart()
        self.telemetry = TelemetryFanout(self.stats, self.chart, self.quality,
                                         self.alert_log, self.integrity)
        self.link = LoggedLink(
            state_model=self.state_model,
            storage_model=self.storage_model,
            telemetry_model=self.telemetry,
            session=self.session,
            integrity_checker=self.integrity,
            alert_log=self.alert_log,
        )
        self.telemetry.link = self.link
        self.commands = CommandSender()

        self._session_open = False
        self._shutdown_done = False
        self._last_status_poll = 0.0
        self._seen_transitions = 0
        self._seen_reboots = 0
        self._last_crc = 0
        self._last_sync = 0
        self._last_nack = 0
        self._last_conn_state = self.link.connection_state
        self._alert_active = {c: False for c in CHANNELS}

    # -- connection ---------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.link.connection_state == "connected"

    def connect(self, port: str, baud: int = 115200) -> str:
        """Open a new session directory and the serial port. Returns the
        session directory path."""
        session_dir = self.session.on_connect(port)
        self.storage_model.reset_counts()
        try:
            self.link.connect(port, baud)
        except Exception:
            self.session.close()
            raise

        self._session_open = True
        self._last_conn_state = self.link.connection_state
        now = time.time()
        self.alert_log.add("GS_EVENT", wall_time=now, message=f"connected to {port}")
        # Open the initial timeline band at the current (assumed Idle) state.
        self.timeline.on_state_change(self.state_model.state, self.state_model.state,
                                      now, self.telemetry.record_count)
        self.send_status()
        return session_dir

    def disconnect(self) -> None:
        self.link.disconnect()
        if self._session_open:
            self.session.close()
            self._session_open = False
        self.alert_log.add("GS_EVENT", message="disconnected")
        self._last_conn_state = self.link.connection_state

    def reset(self) -> str | None:
        """Flush every derived view and counter to a clean slate without
        dropping the serial link. When connected, rolls a fresh session
        directory so recorded files and exports start over too. Returns the
        new session dir, or None if not connected."""
        now = time.time()

        self.alert_log = AlertLog()
        self.state_model = DeviceStateModel()
        self.storage_model = StorageModel()
        self.integrity = IntegrityChecker()
        self.quality = LinkQualityMonitor(alert_log=self.alert_log)
        self.timeline = StateTimeline()
        self.stats = SessionStats()
        self.chart = RollingChart()
        self.telemetry = TelemetryFanout(self.stats, self.chart, self.quality,
                                         self.alert_log, self.integrity)
        self.telemetry.link = self.link

        # point the live link's receive path at the fresh models
        self.link.state_model = self.state_model
        self.link.storage_model = self.storage_model
        self.link.telemetry_model = self.telemetry
        self.link.integrity_checker = self.integrity
        self.link.alert_log = self.alert_log
        self.link._last_seq = None

        session_dir = None
        if self._session_open and self.session.port is not None:
            self.session.close()
            session_dir = self.session.on_connect(self.session.port)
            self.session.records.clear()
            self.session.wall_times.clear()

        # resync bookkeeping; keep the link's own error counters so their
        # deltas stay zero and old errors are not replayed into the fresh log
        self._last_status_poll = 0.0
        self._seen_transitions = 0
        self._seen_reboots = self.quality.reboot_count
        self._last_crc = self.link.crc_error_count
        self._last_sync = self.link.sync_error_count
        self._last_nack = self.link.nack_count
        self._alert_active = {c: False for c in CHANNELS}
        self._last_conn_state = self.link.connection_state

        self.alert_log.add("GS_EVENT", wall_time=now, message="reset")
        if self.connected:
            self.timeline.on_state_change(self.state_model.state,
                                          self.state_model.state, now,
                                          self.telemetry.record_count)
            self.send_status()
        return session_dir

    def shutdown(self) -> None:
        """Idempotent teardown: close the port and session files, and drop the
        alert log and timeline as text next to session.bin."""
        if self._shutdown_done:
            return
        self._shutdown_done = True

        self.link.disconnect()
        session_dir = self.session.dir
        if self._session_open:
            self.session.close()
            self._session_open = False

        if session_dir is not None:
            import os
            try:
                self.alert_log.export_text(os.path.join(session_dir, "alerts.log"))
                self.timeline.export_text(os.path.join(session_dir, "timeline.log"))
            except OSError:
                pass  # exiting anyway; the binary session data is already flushed

    # -- commands -----------------------------------------------------------

    def command_allowed(self, cmd: FrameType) -> bool:
        return self.connected and self.state_model.command_allowed(cmd)

    def send_start(self) -> None:
        self._send(lambda: self.commands.send_start(self.link), "START")

    def send_stop(self) -> None:
        self._send(lambda: self.commands.send_stop(self.link), "STOP")

    def send_status(self) -> None:
        self._send(lambda: self.commands.send_status(self.link), "STATUS")

    def send_replay(self, count: int) -> None:
        self._send(lambda: self.commands.send_replay(self.link, count), f"REPLAY {count}")

    def send_erase(self, magic: int = ERASE_MAGIC) -> None:
        self._send(lambda: self.commands.send_erase(self.link, magic), "ERASE")

    def _send(self, action, label: str) -> None:
        action()
        self.quality.on_command()
        self.alert_log.add("GS_EVENT", message=f"sent {label}")

    # -- frame pump ---------------------------------------------------------

    def pump(self, now: float | None = None) -> int:
        """Drain all buffered frames and update every derived model. Called
        from the UI tick (~20 Hz). Returns the number of frames handled."""
        now = time.time() if now is None else now
        handled = 0

        while True:
            frame = self.link.receive_frame()
            if frame is None:
                break
            handled += 1
            self.quality.on_frame(now)

            if frame.type == FrameType.Status:
                self.quality.on_status(self.storage_model.total_records, now,
                                       seq=self._latest_seq())

        if self.quality.reboot_count > self._seen_reboots:
            self._seen_reboots = self.quality.reboot_count
            self._on_reboot(now)

        self._pump_error_deltas(now)
        self._pump_transitions()
        self._pump_alert_edges(now)
        self._pump_connection_state(now)
        self._maybe_poll_status(now)
        self.quality.update(now)
        return handled

    def _latest_seq(self) -> int | None:
        return self.telemetry.latest.seq if self.telemetry.latest is not None else None

    def _on_reboot(self, now: float) -> None:
        # quality.on_status already logged the REBOOT alert entry (FR-GS-13);
        # mark the charts/timeline and re-issue STATUS to resync.
        seq = self._latest_seq() or 0
        self.chart.reboot_marker(seq)
        self.timeline.on_reboot(seq, now)
        if self.connected:
            try:
                self.send_status()
            except Exception:
                pass  # port may have just dropped; reconnect loop will recover

    def _pump_error_deltas(self, now: float) -> None:
        for _ in range(self.link.crc_error_count - self._last_crc):
            self.quality.on_crc_error()
            self.alert_log.add("CRC_ERROR", wall_time=now, message="frame CRC mismatch")
        for _ in range(self.link.sync_error_count - self._last_sync):
            self.quality.on_sync_error()
            self.alert_log.add("SYNC_ERROR", wall_time=now, message="framing lost")
        for _ in range(self.link.nack_count - self._last_nack):
            self.quality.on_nack()
        self._last_crc = self.link.crc_error_count
        self._last_sync = self.link.sync_error_count
        self._last_nack = self.link.nack_count

    def _pump_transitions(self) -> None:
        transitions = self.state_model.transitions
        for t in transitions[self._seen_transitions:]:
            self.chart.state_marker(t, seq=self._latest_seq())
            self.timeline.on_state_change(t.from_state, t.to_state, t.wall_time,
                                          self.telemetry.record_count)
            self.alert_log.add(
                "STATE_TRANSITION", wall_time=t.wall_time, session_seq=t.session_seq,
                message=(f"{DeviceStateModel.state_name(t.from_state)} -> "
                         f"{DeviceStateModel.state_name(t.to_state)}"))
        self._seen_transitions = len(transitions)

    def _pump_alert_edges(self, now: float) -> None:
        seq = self._latest_seq() or 0
        for channel in CHANNELS:
            active = self.stats.channels[channel].alert_active
            if active == self._alert_active[channel]:
                continue
            self._alert_active[channel] = active
            category = "ALERT_ACTIVE" if active else "ALERT_CLEAR"
            self.alert_log.add(category, wall_time=now, session_seq=seq, message=channel)
            self.timeline.on_alert(channel, active, seq, now)

    def _pump_connection_state(self, now: float) -> None:
        state = self.link.connection_state
        if state != self._last_conn_state:
            recovered = (state == "connected"
                         and self._last_conn_state == "reconnecting")
            self._last_conn_state = state
            self.alert_log.add("GS_EVENT", wall_time=now, message=f"link {state}")
            if recovered:
                # resync device state after an auto-reconnect (FR-GS-13/T10)
                try:
                    self.send_status()
                except Exception:
                    pass

    def _maybe_poll_status(self, now: float) -> None:
        if not self.connected:
            return
        if now - self._last_status_poll < STATUS_POLL_INTERVAL_S:
            return
        self._last_status_poll = now
        try:
            self.send_status()
        except Exception:
            pass  # transient port loss; the reconnect loop handles it


def rebuild_from_session(session: Session) -> tuple[SessionStats, RollingChart]:
    """Recompute stats and a rolling chart from a loaded session's records,
    for the offline session viewer (FR-GS-15)."""
    stats = SessionStats()
    chart = RollingChart()
    for record, wall in zip(session.records, session.wall_times):
        stats.ingest(record, wall)
        chart.update(record)
    return stats, chart
