"""
Ground station session recording. Owns a timestamped directory holding the raw
record stream (session.bin) and a human readable frame log (frames.log), and can
reload a previous session.bin back into records.

session.bin entry layout, little endian:
  32 bytes SensorRecord | float64 wall-clock time

file: groundstation/session.py
author: shalom2552
date: 2026-07-07
"""
from __future__ import annotations

import os
import struct
import time

from .telemetry import RecordDecoder, SensorRecord, RECORD_SIZE, _RECORD_FMT

# One session.bin entry is a 32-byte record followed by a float64 LE wall time.
_WALL_FMT = "<d"
_WALL_SIZE = struct.calcsize(_WALL_FMT)
ENTRY_SIZE = RECORD_SIZE + _WALL_SIZE

_FLUSH_EVERY_N = 16


class Session:
    """A recording session backed by a directory on disk. Live/replay records go
    to session.bin, raw frames to frames.log."""

    def __init__(self, base_dir: str = "sessions") -> None:
        self.base_dir = base_dir
        self.dir: str | None = None
        self.port: str | None = None

        self.records: list[SensorRecord] = []
        self.wall_times: list[float] = []

        self._bin = None
        self._frames = None
        self._since_flush = 0

    def on_connect(self, port: str) -> str:
        """Create sessions/YYYY-MM-DD_HH-MM-SS/ and open its files for writing.
        Returns the session directory path."""
        self.port = port
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        self.dir = os.path.join(self.base_dir, stamp)
        os.makedirs(self.dir, exist_ok=True)

        self._bin = open(os.path.join(self.dir, "session.bin"), "ab")
        self._frames = open(os.path.join(self.dir, "frames.log"), "a")
        self._since_flush = 0
        return self.dir

    def append_record(self, record: SensorRecord, wall_time: float) -> None:
        """Append the 32 record bytes plus an 8-byte float64 LE wall time to
        session.bin. Flushes every 16 records."""
        if self._bin is None:
            raise RuntimeError("session not open; call on_connect first")

        raw = record.raw if len(record.raw) == RECORD_SIZE else _pack_record(record)
        self._bin.write(raw)
        self._bin.write(struct.pack(_WALL_FMT, wall_time))

        self.records.append(record)
        self.wall_times.append(wall_time)

        self._since_flush += 1
        if self._since_flush >= _FLUSH_EVERY_N:
            self._bin.flush()
            self._since_flush = 0

    def append_raw_frame(self, direction: str, frame_bytes: bytes, wall_time: float) -> None:
        """Append a 'wall_time direction hex' line to frames.log."""
        if self._frames is None:
            raise RuntimeError("session not open; call on_connect first")
        self._frames.write(f"{wall_time:.6f} {direction} {frame_bytes.hex()}\n")

    def close(self) -> None:
        """Flush and close session.bin and frames.log."""
        if self._bin is not None:
            self._bin.flush()
            self._bin.close()
            self._bin = None
        if self._frames is not None:
            self._frames.flush()
            self._frames.close()
            self._frames = None

    @classmethod
    def load(cls, path: str) -> "Session":
        """Reconstruct a session from session.bin. path may be the session
        directory or the session.bin file itself. Returns a read-only Session
        with records and wall_times populated."""
        bin_path = path
        if os.path.isdir(path):
            bin_path = os.path.join(path, "session.bin")

        session = cls()
        session.dir = os.path.dirname(bin_path)

        with open(bin_path, "rb") as f:
            data = f.read()

        if len(data) % ENTRY_SIZE != 0:
            raise ValueError(f"session.bin size {len(data)} not a multiple of {ENTRY_SIZE}")

        for off in range(0, len(data), ENTRY_SIZE):
            raw = data[off:off + RECORD_SIZE]
            (wall_time,) = struct.unpack_from(_WALL_FMT, data, off + RECORD_SIZE)
            session.records.append(RecordDecoder.decode(raw))
            session.wall_times.append(wall_time)

        return session


def _pack_record(record: SensorRecord) -> bytes:
    """Re-pack a SensorRecord into its 32-byte wire form when raw is unavailable."""
    return struct.pack(
        _RECORD_FMT,
        record.timestamp, record.ms, record.seq,
        record.lm35_c, record.dht_temp_c, record.dht_hum,
        record.light, record.pot,
        record.alert_bits, record.state, record.fault_bits,
        record.crc32,
    )
