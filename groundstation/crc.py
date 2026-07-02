"""
Ground station CRC-32 calculator for KERN-LITE protocol.

file: groundstation/crc.py
author: shalom2552
date: 2026-02-07
"""

import zlib


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def crc32_update(crc: int, data: bytes) -> int:
    return zlib.crc32(data, crc) & 0xFFFFFFFF
