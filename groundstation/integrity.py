"""Re-validates record-level CRC (transport CRC is already checked by the
frame decoder) and detects sequence gaps in the 16-bit record seq.

INTEGRITY DISTINCTION (spec 7.2): frame CRC protects the serial transport;
record CRC protects the stored 32-byte SensorRecord. A replayed record can
have a valid frame CRC but a corrupted stored payload -- that combination
means storage corruption, not a transport error.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Callable, Optional

from .crc import crc32
from .frame import FrameType

_SEQ_MODULO = 65536


@dataclass
class IntegrityEvent:
    category: str
    message: str
    details: dict


class IntegrityChecker:
    def __init__(self, log_fn: Optional[Callable[[IntegrityEvent], None]] = None):
        # log_fn lets Day 6's AlertLog subscribe without integrity.py
        # depending on it. Defaults to an in-memory list.
        self._log_fn = log_fn
        self.events: list[IntegrityEvent] = []

    def _log(self, category: str, message: str, **details) -> None:
        event = IntegrityEvent(category=category, message=message, details=details)
        self.events.append(event)
        if self._log_fn is not None:
            self._log_fn(event)

    def check_frame(self, frame) -> bool:
        """Only RECORD frames carry a record-level CRC to re-check. Any
        other frame type has already passed frame-CRC validation in the
        decoder, so there's nothing further to verify here."""
        if frame.type != FrameType.Record:
            return True

        payload = frame.payload
        if len(payload) < 32:
            self._log("STORAGE_CORRUPTION_WARNING", "RECORD payload too short",
                       length=len(payload))
            return False

        expected = crc32(payload[0:28])
        stored = struct.unpack_from("<I", payload, 28)[0]
        if expected != stored:
            self._log("STORAGE_CORRUPTION_WARNING",
                       "record CRC mismatch (frame CRC was valid)",
                       expected=expected, stored=stored)
            return False
        return True

    def check_sequence(self, record, last_seq: Optional[int]) -> int:
        """Returns the gap size (0 if contiguous). last_seq=None (first
        record of a session) is never a gap."""
        if last_seq is None:
            return 0

        expected = (last_seq + 1) % _SEQ_MODULO
        if record.seq == expected:
            return 0

        gap = (record.seq - expected) % _SEQ_MODULO
        self._log("SEQ_GAP", f"sequence gap size={gap}",
                   last_seq=last_seq, seq=record.seq, gap=gap)
        return gap
