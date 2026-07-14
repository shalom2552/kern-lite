"""
Decodes 32-byte SensorRecord payloads and tracks running telemetry stats.

This module provides:
- SensorRecord: Dataclass representation of a 32-byte sensor payload with
  temperature, humidity, light, and potentiometer readings.
- RecordDecoder: Unpacks binary payloads into SensorRecord objects.
- TelemetryModel: Aggregates records and maintains per-channel running
  statistics (min, max, mean) and alert tracking.
- _ChannelRunning: Internal class for tracking statistics per sensor channel.

Binary layout (spec sections 9.2/9.3), little-endian:
  u32 timestamp | u16 ms | u16 seq | i16 lm35_c | i16 dht_temp_c |
  u16 dht_hum | u16 light | u16 pot | u8 alert_bits | u8 state |
  u8 fault_bits | 7x reserved | u32 crc32

All temperature values are stored as tenths of degrees Celsius (e.g., 253 = 25.3°C).
Humidity and normalized sensor values are stored as whole numbers (e.g., 450 = 45.0%).

file: groundstation/telemetry.py
author: Yair
date: 2026-06-07
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .crc import crc32

# Binary format string for struct.unpack: little-endian, 32 bytes total
# Breakdown: I=u32, H=u16, h=i16, B=u8, 7x=7 reserved bytes
_RECORD_FMT = "<IHHhhHHHBBB7xI"

RECORD_SIZE = struct.calcsize(_RECORD_FMT)  # Should be exactly 32 bytes
assert RECORD_SIZE == 32, f"SensorRecord format must be 32 bytes, got {RECORD_SIZE}"

# fault_bits masks (spec 9.4)
# Each bit represents a sensor fault condition
FAULT_LM35_RANGE = 0x01  # LM35 reading out of valid range
FAULT_DHT_TIMEOUT = 0x02  # DHT sensor communication timeout
FAULT_DHT_BADDATA = 0x04  # DHT sensor returned invalid data
FAULT_LIGHT_STUCK = 0x08  # Light sensor value unchanged (likely stuck)
FAULT_POT_STUCK = 0x10  # Potentiometer value unchanged (likely stuck)

# Sensor channel names, used as keys in telemetry aggregation
CHANNELS = ("lm35", "dht_temp", "dht_hum", "light", "pot")

# Alert bit masks per channel as (high_bit, low_bit), from spec 9.4
ALERT_MASKS = {
    "lm35": (0x01, 0x02),
    "light": (0x04, 0x08),
    "pot": (0x10, 0x20),
    "dht_temp": (0x40, 0x00),  # spec defines only DHT_TEMP_HI
    "dht_hum": (0x80, 0x00),   # spec defines only DHT_HUM_HI
}


@dataclass
class SensorRecord:
    """Represents a single 32-byte sensor telemetry record.
    
    All temperature and humidity values are stored as tenths of the display value:
      - lm35_c: LM35 temperature in tenths of Celsius (e.g., 253 -> 25.3°C)
      - dht_temp_c: DHT temperature in tenths of Celsius
      - dht_hum: DHT humidity in tenths of percent (e.g., 450 -> 45.0%)
    
    Light and potentiometer are 16-bit unsigned integers (0-65535) that can be
    normalized to [0.0, 1.0] range for comparison across devices.
    
    Attributes:
        timestamp: Unix-style timestamp (seconds)
        ms: Milliseconds component of timestamp
        seq: Sequence number within current session
        lm35_c: Temperature in tenths of degrees Celsius
        dht_temp_c: DHT temperature in tenths of degrees Celsius
        dht_hum: DHT humidity in tenths of percent
        light: Light sensor raw value (0-65535)
        pot: Potentiometer raw value (0-65535)
        alert_bits: Bitmask indicating active alarm conditions
        state: Device state (0=Idle, 1=Recording, 2=Fault)
        fault_bits: Bitmask indicating sensor faults
        crc32: CRC-32 checksum of bytes 0-27
        raw: Original 32-byte payload (not included in repr)
    """
    timestamp: int
    ms: int
    seq: int
    lm35_c: int
    dht_temp_c: int
    dht_hum: int
    light: int
    pot: int
    alert_bits: int
    state: int
    fault_bits: int
    crc32: int
    raw: bytes = field(repr=False, default=b"")

    @property
    def lm35_celsius(self) -> float:
        """Convert LM35 temperature from tenths to decimal Celsius."""
        return self.lm35_c / 10.0

    @property
    def dht_temp_celsius(self) -> float:
        """Convert DHT temperature from tenths to decimal Celsius."""
        return self.dht_temp_c / 10.0

    @property
    def dht_humidity(self) -> float:
        """Convert DHT humidity from tenths to decimal percent."""
        return self.dht_hum / 10.0

    @property
    def light_normalized(self) -> float:
        """Normalize light sensor value to [0.0, 1.0] range for comparison."""
        return self.light / 65535.0

    @property
    def pot_normalized(self) -> float:
        """Normalize potentiometer value to [0.0, 1.0] range for comparison."""
        return self.pot / 65535.0

    def record_crc_valid(self) -> bool:
        """Verify CRC-32 integrity of this record.
        
        Re-computes CRC over bytes 0-27 (excluding the 4-byte CRC field itself)
        and compares against the stored CRC in bytes 28-31 (spec 9.2).
        Returns True if payload is intact, False if corrupted.
        """
        if len(self.raw) != RECORD_SIZE:
            return False
        expected = crc32(self.raw[0:28])  # CRC computed over first 28 bytes
        return expected == self.crc32


def channel_values(record: "SensorRecord") -> dict[str, float]:
    """Per-channel display-unit values of a record, keyed by CHANNELS."""
    return {
        "lm35": record.lm35_celsius,          # Degrees Celsius
        "dht_temp": record.dht_temp_celsius,  # Degrees Celsius
        "dht_hum": record.dht_humidity,       # Percent
        "light": record.light_normalized,     # Normalized [0.0, 1.0]
        "pot": record.pot_normalized,         # Normalized [0.0, 1.0]
    }


class RecordDecoder:
    """Decodes binary SensorRecord payloads into Python dataclass objects."""
    
    @staticmethod
    def decode(payload: bytes) -> SensorRecord:
        """Unpack a 32-byte binary sensor record into a SensorRecord object.
        
        Args:
            payload: Binary record (must be exactly RECORD_SIZE=32 bytes)
        
        Returns:
            SensorRecord with all fields unpacked and validated
        
        Raises:
            ValueError: If payload is not exactly 32 bytes
        """
        if len(payload) != RECORD_SIZE:
            raise ValueError(f"SensorRecord payload must be {RECORD_SIZE} bytes, got {len(payload)}")
        
        # Unpack using the binary format string
        fields = struct.unpack_from(_RECORD_FMT, payload)
        (timestamp, ms, seq, lm35_c, dht_temp_c, dht_hum,
         light, pot, alert_bits, state, fault_bits, crc) = fields
        
        return SensorRecord(
            timestamp=timestamp, ms=ms, seq=seq,
            lm35_c=lm35_c, dht_temp_c=dht_temp_c, dht_hum=dht_hum,
            light=light, pot=pot,
            alert_bits=alert_bits, state=state, fault_bits=fault_bits,
            crc32=crc, raw=bytes(payload),
        )


@dataclass
class _ChannelRunning:
    """Maintains running statistics for a single sensor channel (internal use).
    
    Attributes:
        n: Total number of samples received
        min_val: Minimum value seen (None if no samples yet)
        max_val: Maximum value seen (None if no samples yet)
        mean: Running arithmetic mean (computed incrementally for efficiency)
        alert_active: True if alert condition is currently active
        alert_activations: Number of times alert transitioned from off to on
        time_in_alert_s: Total time spent with alert active (seconds)
        _last_ts: Timestamp of the last update (used for alert duration tracking)
    """
    n: int = 0
    min_val: float | None = None
    max_val: float | None = None
    mean: float = 0.0
    alert_active: bool = False
    alert_activations: int = 0
    time_in_alert_s: float = 0.0
    _last_ts: float | None = None

    def update(self, value: float, alert: bool, wall_time: float) -> None:
        """Update statistics with a new sample value.
        
        Args:
            value: New sensor reading (temperature, humidity, or normalized value)
            alert: Whether an alert condition is active for this sample
            wall_time: Unix timestamp of the sample (used for alert duration tracking)
        """
        self.n += 1
        
        # Update min/max
        if self.min_val is None or value < self.min_val:
            self.min_val = value
        if self.max_val is None or value > self.max_val:
            self.max_val = value
        
        # Update mean incrementally (Welford's online mean) for numerical stability
        # This avoids summing all values and dividing, which can lose precision
        self.mean += (value - self.mean) / self.n

        # Track alert state transitions
        if alert and not self.alert_active:
            # Alert condition just turned on
            self.alert_activations += 1
        
        # Accumulate time spent in alert state
        if self._last_ts is not None and self.alert_active:
            # Add time elapsed since last update (if alert was already on)
            self.time_in_alert_s += max(0.0, wall_time - self._last_ts)
        
        self.alert_active = alert
        self._last_ts = wall_time


class TelemetryModel:
    """Aggregates sensor records and maintains per-channel running statistics.
    
    This class builds a session profile by ingesting SensorRecord objects.
    It tracks:
    - Full list of records received
    - Per-channel min/max/mean values
    - Alert activation counts and total alert duration per channel
    
    Attributes:
        records: List of all SensorRecord objects ingested so far
        channels: Dict mapping channel name to _ChannelRunning statistics
    """

    _ALERT_MASKS = ALERT_MASKS

    def __init__(self) -> None:
        """Initialize an empty telemetry session."""
        self.records: list[SensorRecord] = []
        # Create a _ChannelRunning tracker for each sensor channel
        self.channels: dict[str, _ChannelRunning] = {c: _ChannelRunning() for c in CHANNELS}

    def ingest(self, record: SensorRecord, wall_time: float | None = None) -> None:
        """Add a new sensor record to the session and update channel statistics.
        
        Processes the record to:
        1. Store in the session records list
        2. Extract and normalize sensor values (convert to display units)
        3. Check alert conditions for each channel
        4. Update per-channel min/max/mean/alert statistics
        
        Args:
            record: SensorRecord to ingest
            wall_time: Unix timestamp (uses current time if None)
        """
        import time
        wt = wall_time if wall_time is not None else time.time()
        self.records.append(record)

        # Update statistics for each channel
        for name, value in channel_values(record).items():
            hi_mask, lo_mask = self._ALERT_MASKS[name]
            # Check if either high or low alert bit is set for this channel
            alert = bool(record.alert_bits & (hi_mask | lo_mask))
            self.channels[name].update(value, alert, wt)
