"""
manages the UART connection

file: groundstation/link.py
author: Smallejoo
date: 2026-06-07
"""
import time
import threading
from typing import Optional
import serial

from groundstation.frame import Frame, Decoder, encode, FrameType, CrcError, SyncError


class SerialLink:
    def __init__(self):
        self.ser: Optional[serial.Serial] = None
        self.decoder = Decoder()

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
        # decoder pull complete frames out of the stream.
        if self.ser is None or not self.ser.is_open:
            return None

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

                return frame

        return None

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
