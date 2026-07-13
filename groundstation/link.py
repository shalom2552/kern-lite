"""
manages the UART connection

file: groundstation/link.py
author: Smallejoo
date: 2026-06-07
"""
import time
import threading
from collections import deque
from typing import Optional
import serial

from groundstation.frame import Frame, Decoder, encode, FrameType, CrcError, SyncError


class SerialLink:
    def __init__(self, state_model=None, storage_model=None, telemetry_model=None,
                 session=None, integrity_checker=None, alert_log=None):
        self.ser: Optional[serial.Serial] = None
        self.decoder = Decoder()

        # decoded frames not yet handed to the caller
        self._rx_frames = deque()

        self.rx_count = 0
        self.tx_count = 0
        self.crc_error_count = 0
        self.sync_error_count = 0
        self.nack_count = 0

        self.last_latency_ms: Optional[float] = None
        self._latencies = []

        self.connection_state = "disconnected"

        self._port = None
        self._baud = 115200
        self._running = False
        self._reconnect_thread = None

        self._pending_command_type = None
        self._pending_command_time = None
        self.commands_sent = 0

        # wired receive path. Any of these may stay None, in which case
        # that stage of dispatch is simply skipped -- keeps SerialLink usable
        # fully wired.
        self.state_model = state_model
        self.storage_model = storage_model
        self.telemetry_model = telemetry_model
        self.session = session
        self.integrity_checker = integrity_checker
        self.alert_log = alert_log

        self._in_replay = False  # True between CMD_REPLAY sent and its ACK
        self._last_seq: Optional[int] = None

    @property
    def rolling_avg_latency_ms(self):
        # Keep the average focused on recent replies instead of old startup
        # behavior, so the number reflects the current link quality.
        if not self._latencies:
            return None
        return sum(self._latencies) / len(self._latencies)

    @property
    def nack_rate(self):
        # No commands means no meaningful rejection rate yet.
        if self.commands_sent == 0:
            return 0.0
        return self.nack_count / self.commands_sent

    def connect(self, port: str, baud: int = 115200):
        # Capture the chosen port/baud once, then start the reconnect watcher
        # so transient disconnects can recover with the same settings.
        self._port = port
        self._baud = baud

        self.ser = serial.Serial(port, baudrate=baud, timeout=0.05)
        self.connection_state = "connected"

        self._running = True
        self._reconnect_thread = threading.Thread(
            target=self._auto_reconnect_loop,
            daemon=True
        )
        self._reconnect_thread.start()

    def disconnect(self):
        # Stop the background reconnect loop before closing the port.
        self._running = False
        self.connection_state = "disconnected"

        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass

        self.ser = None

    def record_command(self, command_type: int):
        # Record the command launch time so the next reply can be timed against
        # it without needing explicit frame IDs.
        self._pending_command_type = command_type
        self._pending_command_time = time.time()
        self.commands_sent += 1
        if command_type == FrameType.CmdReplay:
            self._in_replay = True

    def send_frame(self, frame: Frame):
        # Encode the frame before writing so every outbound message follows the
        # same protocol framing as the firmware decoder.
        if self.ser is None or not self.ser.is_open:
            raise RuntimeError("Serial port is not connected")

        data = encode(frame)
        self.ser.write(data)
        self.tx_count += 1

    def receive_frame(self) -> Optional[Frame]:
        # Read whatever bytes are currently buffered, then let the stateful
        # decoder pull complete frames out of the stream. Frames are queued
        # so a chunk holding several of them loses none.
        if self.ser is None or not self.ser.is_open:
            return None

        if not self._rx_frames:
            try:
                data = self.ser.read(self.ser.in_waiting or 1)
            except Exception:
                self.connection_state = "reconnecting"
                return None

            for byte in data:
                try:
                    frame = self.decoder.feed(byte)

                except CrcError:
                    self.crc_error_count += 1
                    continue

                except SyncError:
                    self.sync_error_count += 1
                    continue

                if frame is not None:
                    self._rx_frames.append(frame)

        if not self._rx_frames:
            return None

        frame = self._rx_frames.popleft()
        self.rx_count += 1

        if self._pending_command_time is not None:
            # Associate the first reply after a command with that
            # command to produce a command-to-response latency figure.
            self.last_latency_ms = (time.time() - self._pending_command_time) * 1000
            self._latencies.append(self.last_latency_ms)

            if len(self._latencies) > 20:
                self._latencies.pop(0)

            self._pending_command_time = None

        #  real NACK is 0x21 / FrameType.Nack
        if frame.type == FrameType.Nack:
            self.nack_count += 1

        self._dispatch(frame)
        return frame

    def _dispatch(self, frame: Frame) -> None:
        # route each frame type to its model per spec 7.2 / FR-GS-07.
        # RECORD  -> integrity re-check -> telemetry ingest -> session append
        #            -> live/replay counter on StorageModel
        # STATUS  -> DeviceStateModel + StorageModel
        # NACK    -> decode NackCode, log to alert history
        if frame.type == FrameType.Record:
            self._dispatch_record(frame)
        elif frame.type == FrameType.Status:
            self._dispatch_status(frame)
        elif frame.type == FrameType.Nack:
            self._dispatch_nack(frame)
        elif frame.type == FrameType.Ack:
            # ACK closes any in-flight REPLAY transaction (spec 7.2).
            self._in_replay = False

    def _dispatch_record(self, frame: Frame) -> None:
        from groundstation.telemetry import RecordDecoder

        wall_time = time.time()

        if self.integrity_checker is not None:
            # Frame CRC already passed (decoder wouldn't have returned a
            # Frame otherwise); this re-checks the record-level CRC and
            # logs STORAGE_CORRUPTION_WARNING internally if it fails.
            self.integrity_checker.check_frame(frame)

        record = RecordDecoder.decode(frame.payload)

        if self.integrity_checker is not None:
            self.integrity_checker.check_sequence(record, self._last_seq)
        self._last_seq = record.seq

        if self.telemetry_model is not None:
            self.telemetry_model.ingest(record, wall_time=wall_time)

        if self.session is not None:
            self.session.append_record(record, wall_time)

        if self.storage_model is not None:
            if self._in_replay:
                self.storage_model.note_replay_record()
            else:
                self.storage_model.note_live_record()

    def _dispatch_status(self, frame: Frame) -> None:
        if self.state_model is not None:
            self.state_model.update_from_status(frame)
        if self.storage_model is not None:
            self.storage_model.update_from_status(frame)

    def _dispatch_nack(self, frame: Frame) -> None:
        from groundstation.frame import NackCode

        code_raw = frame.payload[0] if frame.payload else None
        try:
            code = NackCode(code_raw)
        except (TypeError, ValueError):
            code = code_raw

        if self.alert_log is not None:
            self.alert_log.add("NACK", code=code, command=self._pending_command_type)

    def _auto_reconnect_loop(self):
        # Run until disconnect() clears the flag, reopening the port whenever
        # the serial handle disappears or stops reporting as open.
        while self._running:
            if self.ser is None or not self.ser.is_open:
                self.connection_state = "reconnecting"

                try:
                    # Recreate the serial object with the last known connection
                    # settings instead of requiring the caller to rebuild state.
                    self.ser = serial.Serial(
                        self._port,
                        baudrate=self._baud,
                        timeout=0.05
                    )
                    self.connection_state = "connected"
                except Exception:
                    time.sleep(2)
                    continue

            time.sleep(2)
