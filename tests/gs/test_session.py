"""
Tests for groundstation.session.Session: record round-trip through session.bin
and monotonic wall-clock timestamps.

file: tests/gs/test_session.py
author: shalom2552
date: 2026-07-07
"""
import struct

from groundstation.crc import crc32
from groundstation.telemetry import RECORD_SIZE, RecordDecoder
from groundstation.session import Session


def make_record(seq: int):
    body = struct.pack(
        "<IHHhhHHHBBB7x",
        1000 + seq, seq % 1000, seq,   # timestamp, ms, seq
        250, 222, 450,                 # lm35_c, dht_temp_c, dht_hum
        32768, 6553,                   # light, pot
        0, 1, 0,                       # alert_bits, state, fault_bits
    )
    payload = body + struct.pack("<I", crc32(body))
    assert len(payload) == RECORD_SIZE
    return RecordDecoder.decode(payload)


def test_record_roundtrip(tmp_path):
    sess = Session(base_dir=str(tmp_path))
    sess.on_connect("COM_TEST")

    for seq in range(1, 11):
        sess.append_record(make_record(seq), wall_time=float(seq))
    sess.close()

    reloaded = Session.load(sess.dir)

    assert len(reloaded.records) == 10
    for i, rec in enumerate(reloaded.records, start=1):
        assert rec.seq == i
        assert rec.record_crc_valid()
        assert rec.raw == make_record(i).raw


def test_wall_times_monotonic(tmp_path):
    sess = Session(base_dir=str(tmp_path))
    sess.on_connect("COM_TEST")

    for seq in range(1, 11):
        sess.append_record(make_record(seq), wall_time=float(seq) * 0.5)
    sess.close()

    reloaded = Session.load(sess.dir)

    assert len(reloaded.wall_times) == 10
    for prev, cur in zip(reloaded.wall_times, reloaded.wall_times[1:]):
        assert cur > prev


def test_load_from_bin_path(tmp_path):
    sess = Session(base_dir=str(tmp_path))
    sess.on_connect("COM_TEST")
    sess.append_record(make_record(1), wall_time=1.0)
    sess.append_record(make_record(2), wall_time=2.0)
    sess.close()

    import os
    reloaded = Session.load(os.path.join(sess.dir, "session.bin"))
    assert [r.seq for r in reloaded.records] == [1, 2]


def test_frames_log_written(tmp_path):
    sess = Session(base_dir=str(tmp_path))
    sess.on_connect("COM_TEST")
    sess.append_raw_frame("tx", b"\xab\x01\x02", wall_time=1.5)
    sess.close()

    import os
    with open(os.path.join(sess.dir, "frames.log")) as f:
        line = f.readline().strip()
    parts = line.split()
    assert parts[1] == "tx"
    assert parts[2] == "ab0102"
