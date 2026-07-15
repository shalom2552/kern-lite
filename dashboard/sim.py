"""
Device simulator for exercising the dashboard without hardware.

Opens a pty pair, prints the slave path, and speaks the KERN-LITE protocol on
the master side: replies ACK/STATUS/NACK to commands (including BadMagic on a
wrong erase magic), streams 10 Hz RECORD frames while Recording, and serves
REPLAY from a simulated ring. Sensor values wander with occasional threshold
excursions so alerts, shading, and stats have something to show.

Run with:
  python -m dashboard.sim
then connect the dashboard to the printed path.

file: dashboard/sim.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import math
import os
import random
import select
import struct
import time
import tty

from groundstation.crc import crc32
from groundstation.frame import (Decoder, Frame, FrameType, NackCode,
                                 CrcError, SyncError, encode)
from groundstation.telemetry import ALERT_MASKS, _RECORD_FMT

ERASE_MAGIC = 0xDEADC0DE
RECORD_HZ = 10.0
FILE_COUNT = 4
RECORDS_PER_FILE = 256

# Occasional artificial impairments so the dashboard's gap/alert paths light up.
GAP_PROBABILITY = 0.002
ALERT_WAVE_PERIOD_S = 45.0


class SimDevice:
    def __init__(self) -> None:
        self.state = 0  # 0 Idle, 1 Recording, 2 Fault
        self.seq = 0
        self.total_records = 0
        self.wrap_count = 0
        self.start_time = time.time()
        self.ring: list[bytes] = []  # last FILE_COUNT*RECORDS_PER_FILE payloads

    # -- record generation ----------------------------------------------------

    def make_record_payload(self) -> bytes:
        now = time.time()
        uptime = now - self.start_time
        phase = 2 * math.pi * uptime

        # Slow waves around comfortable values; a long secondary wave pushes
        # lm35 and light past their thresholds every ALERT_WAVE_PERIOD_S.
        excursion = math.sin(2 * math.pi * uptime / ALERT_WAVE_PERIOD_S)
        lm35 = 25.0 + 5.0 * math.sin(phase / 20) + 18.0 * max(0.0, excursion - 0.7) / 0.3
        dht_temp = 24.0 + 3.0 * math.sin(phase / 33 + 1.0)
        dht_hum = 45.0 + 10.0 * math.sin(phase / 27 + 2.0)
        light = 0.5 + 0.3 * math.sin(phase / 15) + 0.6 * max(0.0, -excursion - 0.7) / 0.3
        pot = 0.5 + 0.45 * math.sin(phase / 9)

        lm35 += random.gauss(0, 0.15)
        dht_temp += random.gauss(0, 0.1)
        dht_hum += random.gauss(0, 0.4)
        light = min(1.0, max(0.0, light + random.gauss(0, 0.01)))
        pot = min(1.0, max(0.0, pot + random.gauss(0, 0.005)))

        alert_bits = self._alert_bits(lm35, dht_temp, dht_hum, light, pot)

        body = struct.pack(
            _RECORD_FMT,
            int(uptime), int((uptime % 1) * 1000), self.seq,
            int(lm35 * 10), int(dht_temp * 10), int(dht_hum * 10),
            int(light * 65535), int(pot * 65535),
            alert_bits, self.state, 0,
            0,  # placeholder crc, patched below
        )
        return body[:28] + struct.pack("<I", crc32(body[:28]))

    @staticmethod
    def _alert_bits(lm35: float, dht_temp: float, dht_hum: float,
                    light: float, pot: float) -> int:
        # Thresholds mirror firmware/system/config.hpp (see chart.py).
        thresholds = {
            "lm35": (lm35, 10.0, 40.0),
            "dht_temp": (dht_temp, 5.0, 45.0),
            "dht_hum": (dht_hum, 10.0, 90.0),
            "light": (light, 0.05, 0.95),
            "pot": (pot, 0.02, 0.98),
        }
        bits = 0
        for channel, (value, lo, hi) in thresholds.items():
            hi_mask, lo_mask = ALERT_MASKS[channel]
            if value > hi:
                bits |= hi_mask
            elif value < lo:
                bits |= lo_mask
        return bits

    def next_record_frame(self) -> Frame:
        if random.random() < GAP_PROBABILITY:
            self.seq = (self.seq + random.randint(2, 5)) & 0xFFFF  # simulated drop
        payload = self.make_record_payload()
        self.seq = (self.seq + 1) & 0xFFFF
        self.total_records += 1
        self.ring.append(payload)
        capacity = FILE_COUNT * RECORDS_PER_FILE
        if len(self.ring) > capacity:
            self.ring.pop(0)
        if self.total_records and self.total_records % capacity == 0:
            self.wrap_count += 1
        return Frame(FrameType.Record, payload)

    # -- command handling ------------------------------------------------------

    def status_payload(self) -> bytes:
        records_in_file = self.total_records % RECORDS_PER_FILE
        current_file = (self.total_records // RECORDS_PER_FILE) % FILE_COUNT
        return struct.pack("<BBBBIIH", self.state, 1, FILE_COUNT, current_file,
                           self.total_records, self.wrap_count, records_in_file)

    def handle_command(self, frame: Frame) -> list[Frame]:
        t = frame.type
        if t == FrameType.CmdStatus:
            return [Frame(FrameType.Status, self.status_payload())]

        if t == FrameType.CmdStart:
            if self.state != 0:
                return [Frame(FrameType.Nack, bytes([NackCode.InvalidState]))]
            self.state = 1
            return [Frame(FrameType.Ack), Frame(FrameType.Status, self.status_payload())]

        if t == FrameType.CmdStop:
            if self.state != 1:
                return [Frame(FrameType.Nack, bytes([NackCode.InvalidState]))]
            self.state = 0
            return [Frame(FrameType.Ack), Frame(FrameType.Status, self.status_payload())]

        if t == FrameType.CmdReplay:
            if self.state != 0:
                return [Frame(FrameType.Nack, bytes([NackCode.InvalidState]))]
            count = int.from_bytes(frame.payload[:2], "little") if len(frame.payload) >= 2 else 0
            replayed = [Frame(FrameType.Record, p) for p in self.ring[-count:]]
            # Records first, then ACK: the GS marks records as replay until ACK.
            return replayed + [Frame(FrameType.Ack)]

        if t == FrameType.CmdErase:
            if self.state != 0:
                return [Frame(FrameType.Nack, bytes([NackCode.InvalidState]))]
            magic = int.from_bytes(frame.payload[:4], "little") if len(frame.payload) >= 4 else 0
            if magic != ERASE_MAGIC:
                return [Frame(FrameType.Nack, bytes([NackCode.BadMagic]))]
            self.ring.clear()
            self.total_records = 0
            self.wrap_count = 0
            return [Frame(FrameType.Ack), Frame(FrameType.Status, self.status_payload())]

        return [Frame(FrameType.Nack, bytes([NackCode.BadCommand]))]


def main() -> None:
    master_fd, slave_fd = os.openpty()
    tty.setraw(slave_fd)  # no echo: the GS must only see what the sim sends
    os.set_blocking(master_fd, False)
    print(f"KERN-LITE device simulator on: {os.ttyname(slave_fd)}")
    print("Connect the dashboard to that path. Ctrl+C to stop.")

    device = SimDevice()
    decoder = Decoder()
    next_record = time.time()

    def send(frames: list[Frame]) -> None:
        for frame in frames:
            os.write(master_fd, encode(frame))

    try:
        while True:
            readable, _, _ = select.select([master_fd], [], [], 0.02)
            if readable:
                try:
                    data = os.read(master_fd, 4096)
                except (BlockingIOError, OSError):
                    data = b""
                for byte in data:
                    try:
                        frame = decoder.feed(byte)
                    except (CrcError, SyncError):
                        continue
                    if frame is not None:
                        print(f"<- {frame.type.name}")
                        send(device.handle_command(frame))

            now = time.time()
            if device.state == 1 and now >= next_record:
                next_record = now + 1.0 / RECORD_HZ
                send([device.next_record_frame()])
    except KeyboardInterrupt:
        print("\nsimulator stopped")
    finally:
        os.close(master_fd)
        os.close(slave_fd)


if __name__ == "__main__":
    main()
