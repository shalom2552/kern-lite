"""
Tests for RecordDecoder, TelemetryModel, and DeviceStateModel.

file: tests/gs/test_telemetry.py
"""
import struct

from groundstation.crc import crc32
from groundstation.frame import Frame, FrameType
from groundstation.telemetry import RECORD_SIZE, RecordDecoder, TelemetryModel
from groundstation.state import DeviceStateModel, STATE_IDLE, STATE_RECORDING, STATE_FAULT


def make_record_bytes(timestamp, ms, seq, lm35_c, dht_temp_c, dht_hum,
                       light, pot, alert_bits, state, fault_bits):
    body = struct.pack(
        "<IHHhhHHHBBB7x",
        timestamp, ms, seq, lm35_c, dht_temp_c, dht_hum,
        light, pot, alert_bits, state, fault_bits,
    )
    crc = crc32(body)
    return body + struct.pack("<I", crc)


def test_decode_hand_crafted_record():
    payload = make_record_bytes(
        timestamp=1000, ms=250, seq=5,
        lm35_c=253, dht_temp_c=222, dht_hum=450,
        light=32768, pot=6553,
        alert_bits=0, state=1, fault_bits=0,
    )
    assert len(payload) == RECORD_SIZE

    rec = RecordDecoder.decode(payload)

    assert rec.timestamp == 1000
    assert rec.ms == 250
    assert rec.seq == 5
    assert rec.lm35_c == 253
    assert rec.dht_temp_c == 222
    assert rec.dht_hum == 450
    assert rec.light == 32768
    assert rec.pot == 6553
    assert rec.state == 1

    assert abs(rec.lm35_celsius - 25.3) < 1e-6
    assert abs(rec.dht_temp_celsius - 22.2) < 1e-6
    assert abs(rec.dht_humidity - 45.0) < 1e-6
    assert abs(rec.light_normalized - (32768 / 65535.0)) < 1e-9
    assert abs(rec.pot_normalized - (6553 / 65535.0)) < 1e-9


def test_record_crc_valid():
    payload = make_record_bytes(
        timestamp=1000, ms=250, seq=5,
        lm35_c=253, dht_temp_c=222, dht_hum=450,
        light=32768, pot=6553,
        alert_bits=0, state=1, fault_bits=0,
    )
    expected = crc32(payload[0:28])
    assert expected == struct.unpack_from("<I", payload, 28)[0]

    rec = RecordDecoder.decode(payload)
    assert rec.record_crc_valid()

    corrupted = bytearray(payload)
    corrupted[10] ^= 0xFF
    rec_bad = RecordDecoder.decode(bytes(corrupted))
    assert not rec_bad.record_crc_valid()


def test_telemetry_model_min_max_mean():
    model = TelemetryModel()

    lm35_values = [200, 210, 220, 230, 240]  # tenths of degC -> 20.0..24.0
    for i, lm35_c in enumerate(lm35_values):
        payload = make_record_bytes(
            timestamp=1000 + i, ms=0, seq=i,
            lm35_c=lm35_c, dht_temp_c=0, dht_hum=0,
            light=0, pot=0,
            alert_bits=0, state=1, fault_bits=0,
        )
        rec = RecordDecoder.decode(payload)
        model.ingest(rec, wall_time=float(i))

    stats = model.channels["lm35"]
    assert stats.n == 5
    assert abs(stats.min_val - 20.0) < 1e-6
    assert abs(stats.max_val - 24.0) < 1e-6
    assert abs(stats.mean - 22.0) < 1e-6


def test_device_state_transitions():
    model = DeviceStateModel()

    def status(state):
        payload = bytes([state, 1]) + bytes(12)
        return Frame(type=FrameType.Status, payload=payload)

    model.update_from_status(status(STATE_RECORDING))  # 0 -> 1
    model.update_from_status(status(STATE_IDLE))        # 1 -> 0
    model.update_from_status(status(STATE_FAULT))        # 0 -> 2

    assert len(model.transitions) == 3
    assert all(t.duration_in_prev >= 0.0 for t in model.transitions)
    assert [t.to_state for t in model.transitions] == [STATE_RECORDING, STATE_IDLE, STATE_FAULT]


def test_command_gating_in_recording():
    model = DeviceStateModel()
    payload = bytes([STATE_RECORDING, 1]) + bytes(12)
    model.update_from_status(Frame(type=FrameType.Status, payload=payload))

    assert model.state == STATE_RECORDING
    assert not model.command_allowed(FrameType.CmdStart)
    assert model.command_allowed(FrameType.CmdStop)
