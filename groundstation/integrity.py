"""
Integrity checking for decoded telemetry records.

file: groundstation/integrity.py
author: Yair
date: 2026-12-07
"""
from __future__ import annotations

import logging
import struct

from groundstation.crc import crc32
from groundstation.frame import Frame, FrameType
from groundstation.telemetry import RECORD_SIZE
from groundstation.telemetry import SensorRecord


logger = logging.getLogger(__name__)


class IntegrityChecker:
    """Validate record-level integrity on top of the already-decoded frame.

    The frame decoder already guarantees framing and frame CRC correctness.
    This helper adds the next layer up: record payload integrity for RECORD
    frames and sequence continuity checks for decoded sensor records.
    """

    def check_frame(self, frame: Frame) -> bool:
        """Re-check the CRC stored inside a decoded RECORD payload.

        For non-RECORD frames there is no record-level payload to validate, so
        the method treats them as already acceptable. For RECORD frames, the
        payload must be a complete 32-byte SensorRecord buffer and its embedded
        CRC must match the CRC computed over bytes 0..27.
        """
        if frame.type != FrameType.Record:
            return True

        if len(frame.payload) != RECORD_SIZE:
            logger.warning("STORAGE_CORRUPTION_WARNING")
            return False

        payload = frame.payload
        stored_crc = struct.unpack_from("<I", payload, 28)[0]
        computed_crc = crc32(payload[0:28])

        if computed_crc != stored_crc:
            logger.warning("STORAGE_CORRUPTION_WARNING")
            return False

        return True

    def check_sequence(self, record: SensorRecord, last_seq: int) -> int:
        """Report how many sequence numbers were skipped before this record.

        The sequence counter is 16-bit and wraps at 65536, so the expected next
        value is computed modulo 65536. If the record does not follow that
        expected value exactly, the returned gap size is the distance between
        the expected value and the received value in modulo arithmetic.
        """
        expected_seq = (last_seq + 1) % 65536
        if record.seq == expected_seq:
            return 0

        gap_size = (record.seq - expected_seq) % 65536
        logger.warning("SEQ_GAP size=%d", gap_size)
        return gap_size
