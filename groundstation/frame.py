"""
Protocol framing and codec for KERN-LITE.

file: groundstation/frame.py
author: shalom2552
date: 2026-02-07
"""
from crc import crc32
from enum import IntEnum
from typing import Optional
from dataclasses import dataclass

STX = 0xAB
ETX = 0xCD
MAX_PAYLOAD = 256
FRAME_OVERHEAD = 8

class FrameType(IntEnum):
    CmdStart = 0x01
    CmdStop = 0x02
    CmdStatus = 0x03
    CmdReplay = 0x04
    CmdErase = 0x06
    Status = 0x10
    Record = 0x11
    Ack = 0x20
    Nack = 0x21

class NackCode(IntEnum):
    BadCommand = 1
    InvalidState = 2
    BadLength = 3
    BadMagic = 4
    StorageError = 5


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

def encode(frame: Frame) -> bytes:
    # TODO: Implement the encoding logic
    return b''

class CrcError(Exception):
    pass

class SyncError(Exception):
    pass

class Decoder:

    def feed(self, byte: int) -> Optional[Frame]:
        """
        Returning a Frame when complete or None.
        raising CrcError or SyncError exceptions.
        Mirror the firmware state machine exactly
        """
        # TODO: Implement the decoding logic
        return None
