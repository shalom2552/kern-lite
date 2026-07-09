"""
Ground station storage panel model. Decodes STATUS frames into ring state and
exposes a per-file view for the UI, plus live/replay record counters.

file: groundstation/storage_panel.py
author: shalom2552
date: 2026-07-07
"""
from __future__ import annotations

import struct

from .frame import Frame

# Firmware ring geometry (matches firmware/storage/circular_log.hpp).
LOG_FILE_COUNT = 4
RECORDS_PER_FILE = 256

# STATUS payload is 14 bytes, little endian (spec 8.5):
#   u8 state | u8 sd_mounted | u8 file_count | u8 current_file |
#   u32 total_records | u32 wrap_count | u16 records_in_file
_STATUS_FMT = "<BBBBIIH"
STATUS_SIZE = struct.calcsize(_STATUS_FMT)
assert STATUS_SIZE == 14, f"STATUS payload must be 14 bytes, got {STATUS_SIZE}"


class StorageModel:
    """Holds the latest storage state reported by the device and the counts of
    records the ground station has received live and via replay."""

    def __init__(self) -> None:
        self.state: int = 0
        self.sd_mounted: bool = False
        self.file_count: int = 0
        self.current_file: int = 0
        self.total_records: int = 0
        self.wrap_count: int = 0
        self.records_in_file: int = 0

        self.live_record_count: int = 0
        self.replay_record_count: int = 0

    def update_from_status(self, frame: Frame) -> None:
        """Decode a 14-byte STATUS payload into the model fields."""
        payload = frame.payload
        if len(payload) != STATUS_SIZE:
            raise ValueError(f"STATUS payload must be {STATUS_SIZE} bytes, got {len(payload)}")

        (state, sd_mounted, file_count, current_file,
         total_records, wrap_count, records_in_file) = struct.unpack(_STATUS_FMT, payload)

        self.state = state
        self.sd_mounted = bool(sd_mounted)
        self.file_count = file_count
        self.current_file = current_file
        self.total_records = total_records
        self.wrap_count = wrap_count
        self.records_in_file = records_in_file

    def ring_visual(self) -> list[dict]:
        """One dict per log file for the UI ring display:
        {index, is_current, is_wrapped, record_count}.

        Before the first wrap only files 0..current_file hold records: files
        below current are full, the current file holds records_in_file, files
        above it are empty. After the first wrap the whole ring has been filled,
        so every file is full except the current one being overwritten.
        """
        count = self.file_count or LOG_FILE_COUNT
        wrapped = self.wrap_count > 0
        out: list[dict] = []

        for i in range(count):
            if i == self.current_file:
                record_count = self.records_in_file
            elif wrapped or i < self.current_file:
                record_count = RECORDS_PER_FILE
            else:
                record_count = 0

            out.append({
                "index": i,
                "is_current": i == self.current_file,
                "is_wrapped": wrapped,
                "record_count": record_count,
            })

        return out

    def note_live_record(self) -> None:
        """Count one record received from the live RECORD stream."""
        self.live_record_count += 1

    def note_replay_record(self) -> None:
        """Count one record received in response to a REPLAY command."""
        self.replay_record_count += 1

    def reset_counts(self) -> None:
        """Clear the live and replay counters (e.g. on a new session)."""
        self.live_record_count = 0
        self.replay_record_count = 0
