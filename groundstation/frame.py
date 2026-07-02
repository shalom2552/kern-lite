"""
Protocol framing and codec for KERN-LITE.

file: groundstation/frame.py
author: shalom2552
date: 2026-02-07
"""

import struct
from groundstation.crc import crc32, crc32_update
from enum import IntEnum, Enum, auto
from typing import Optional
from dataclasses import dataclass


STX = 0xAB
ETX = 0xCD
MAX_PAYLOAD = 256
FRAME_OVERHEAD = 9


class FrameType(IntEnum):
    CmdStart = 0x01
    CmdStop = 0x02
    CmdStatus = 0x03
    CmdReplay = 0x04
    CmdErase = 0x06
    Status = 0x12
    Record = 0x10
    Ack = 0x20
    Nack = 0x21


class NackCode(IntEnum):
    CrcError = 1
    BadCommand = 2
    InvalidState = 3
    StorageError = 4
    BadMagic = 6


@dataclass
class Frame:
    type: FrameType
    payload: bytes = b''
    state: int = 0
    sd_mounted: bool = False
    file_count: int = 0
    current_file: int = 0
    total_records: int = 0
    wrap_count: int = 0
    records_in_file: int = 0


class CrcError(Exception):
    pass


class SyncError(Exception):
    pass


def encode(frame: Frame) -> bytes:
    payload_len = len(frame.payload)
    header = struct.pack('<BH', frame.type.value, payload_len)
    crc_data = header + frame.payload
    crc_val = crc32(crc_data)
    return bytes([STX]) + crc_data + struct.pack('<I', crc_val) + bytes([ETX])


class Decoder:
    class _State(Enum):
        WAIT_STX = auto()
        TYPE = auto()
        LEN_LO = auto()
        LEN_HI = auto()
        PAYLOAD = auto()
        CRC0 = auto()
        CRC1 = auto()
        CRC2 = auto()
        CRC3 = auto()
        WAIT_ETX = auto()

    def __init__(self):
        self._state = self._State.WAIT_STX
        self._type = 0
        self._len = 0
        self._payload = bytearray()
        self._crc_calc = 0
        self._crc_recv = bytearray()

    def reset(self):
        self.__init__()

    def feed(self, byte: int) -> Optional[Frame]:
        """
        Returning a Frame when complete or None.
        raising CrcError or SyncError exceptions.
        Mirror the firmware state machine exactly
        """
        S = self._State
        if self._state == S.WAIT_STX:
            if byte == STX:
                self._state = S.TYPE

        elif self._state == S.TYPE:
            self._type = byte
            self._crc_calc = crc32_update(0, bytes([byte]))
            self._state = S.LEN_LO

        elif self._state == S.LEN_LO:
            self._len = byte
            self._crc_calc = crc32_update(self._crc_calc, bytes([byte]))
            self._state = S.LEN_HI

        elif self._state == S.LEN_HI:
            self._len |= byte << 8
            self._crc_calc = crc32_update(self._crc_calc, bytes([byte]))
            if self._len > MAX_PAYLOAD:
                self.reset()
                raise SyncError(f"len {self._len} > {MAX_PAYLOAD}")
            self._payload = bytearray()
            self._state = S.PAYLOAD if self._len else S.CRC0

        elif self._state == S.PAYLOAD:
            self._payload.append(byte)
            self._crc_calc = crc32_update(self._crc_calc, bytes([byte]))
            if len(self._payload) == self._len:
                self._state = S.CRC0

        elif self._state == S.CRC0:
            self._crc_recv = bytearray([byte])
            self._state = S.CRC1
        elif self._state == S.CRC1:
            self._crc_recv.append(byte)
            self._state = S.CRC2
        elif self._state == S.CRC2:
            self._crc_recv.append(byte)
            self._state = S.CRC3
        elif self._state == S.CRC3:
            self._crc_recv.append(byte)
            self._state = S.WAIT_ETX

        elif self._state == S.WAIT_ETX:
            recv = struct.unpack('<I', bytes(self._crc_recv))[0]
            calc = self._crc_calc & 0xFFFFFFFF
            ftype_raw, payload, ok_etx = self._type, bytes(self._payload), byte == ETX
            self.reset()
            if recv != calc:
                raise CrcError(f"crc mismatch calc={calc:#x} recv={recv:#x}")
            if not ok_etx:
                raise SyncError(f"bad etx {byte:#x}")
            try:
                ftype = FrameType(ftype_raw)
            except ValueError:
                raise SyncError(f"unknown type {ftype_raw:#x}")
            return Frame(type=ftype, payload=payload)

        return None
