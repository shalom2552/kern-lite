# Ground Station Interactive REPL

Talk to the board by hand from a Python REPL — connect, send commands, read frames — instead of running a fixed script. Run from repo root with the venv interpreter (see `docs/README.md` for first-time venv setup).

```bash
.venv/bin/python
```

## Setup (paste first, every session)

```python
from groundstation.link import SerialLink
from groundstation.commands import CommandSender
from groundstation.frame import Frame, FrameType, NackCode
from groundstation.telemetry import RecordDecoder

link = SerialLink()
cmd = CommandSender()
link.connect("/dev/ttyACM0", 115200)   # port, baud
```

`link.disconnect()` when done.

## Commands — templated calls

`CommandSender` builds + sends the frame in one call, no manual encoding needed:

| Command | Call | Valid state | Notes |
|---|---|---|---|
| START | `cmd.send_start(link)` | Idle | begins recording |
| STOP | `cmd.send_stop(link)` | Recording | stops recording |
| STATUS | `cmd.send_status(link)` | any | requests board state |
| REPLAY | `cmd.send_replay(link, n)` | Idle, SD mounted | `n` = record count (u16), board streams `n` old `Record` frames then `Ack` |
| ERASE | `cmd.send_erase(link, 0xDEADC0DE)` | Idle | magic value is fixed, wrong magic -> `NACK BadMagic` |

Raw/custom frame (e.g. to deliberately trigger `NACK BadCommand`):

```python
link.record_command(0xFF)          # bookkeeping for latency tracking
link.send_frame(Frame(0xFF, b""))
```

## Reading replies

`link.receive_frame()` is non-blocking — returns one decoded `Frame` or `None`. Poll it in a small loop:

```python
import time

def read_reply(timeout_s=2.0, skip_records=True):
    end = time.time() + timeout_s
    while time.time() < end:
        f = link.receive_frame()
        if f is None:
            time.sleep(0.01)
            continue
        if skip_records and f.type == FrameType.Record:
            continue
        return f
    return None
```

```python
>>> cmd.send_start(link)
>>> read_reply()
Frame(type=<FrameType.Ack: 32>, payload=b'')
```

## STATUS payload (14 bytes)

```python
def parse_status(payload: bytes):
    return {
        "state": payload[0],           # 0=Idle 1=Recording 2=Fault
        "sd_mounted": payload[1],
        "file_count": payload[2],
        "current_file": payload[3],
        "total_records": int.from_bytes(payload[4:8], "little"),
        "wrap_count": int.from_bytes(payload[8:12], "little"),
        "records_in_file": int.from_bytes(payload[12:14], "little"),
    }
```

```python
>>> cmd.send_status(link)
>>> f = read_reply()
>>> parse_status(f.payload)
{'state': 0, 'sd_mounted': 1, 'file_count': 1, 'current_file': 0, 'total_records': 120, 'wrap_count': 0, 'records_in_file': 120}
```

## Reading RECORD frames (live stream or REPLAY)

```python
>>> f = link.receive_frame()
>>> f.type == FrameType.Record
True
>>> rec = RecordDecoder.decode(f.payload)
>>> rec.lm35_celsius, rec.dht_temp_celsius, rec.dht_humidity, rec.light_normalized, rec.pot_normalized
(24.3, 23.9, 45.2, 0.512, 0.884)
>>> rec.seq, rec.alert_bits, rec.fault_bits
(41, 0, 0)
>>> rec.record_crc_valid()
True
```

Collect a batch (e.g. after REPLAY):

```python
def collect_records(n, timeout_s=10.0):
    out = []
    end = time.time() + timeout_s
    while time.time() < end and len(out) < n:
        f = link.receive_frame()
        if f is None:
            time.sleep(0.005)
            continue
        if f.type == FrameType.Record:
            out.append(RecordDecoder.decode(f.payload))
    return out
```

## Link counters (introspection any time)

```python
>>> link.tx_count, link.rx_count
>>> link.crc_error_count, link.sync_error_count
>>> link.nack_count, link.nack_rate
>>> link.last_latency_ms, link.rolling_avg_latency_ms
```

## Frame type / NACK code reference

`FrameType`:

| Name | Value | Direction |
|---|---|---|
| `CmdStart` | `0x01` | host → board |
| `CmdStop` | `0x02` | host → board |
| `CmdStatus` | `0x03` | host → board |
| `CmdReplay` | `0x04` | host → board, payload = record count (u16 LE) |
| `CmdErase` | `0x06` | host → board, payload = magic `0xDEADC0DE` (u32 LE) |
| `Status` | `0x12` | board → host, 14-byte payload |
| `Record` | `0x10` | board → host, 32-byte payload |
| `Ack` | `0x20` | board → host |
| `Nack` | `0x21` | board → host, `payload[0]` = `NackCode` |

`NackCode`: `1`=CrcError, `2`=BadCommand, `3`=InvalidState, `4`=StorageError, `6`=BadMagic.

Device states: `0`=Idle, `1`=Recording, `2`=Fault.

## Full worked example (paste as one block)

```python
from groundstation.link import SerialLink
from groundstation.commands import CommandSender
from groundstation.frame import Frame, FrameType, NackCode
from groundstation.telemetry import RecordDecoder
import time

link = SerialLink()
cmd = CommandSender()
link.connect("/dev/ttyACM0", 115200)

def read_reply(timeout_s=2.0, skip_records=True):
    end = time.time() + timeout_s
    while time.time() < end:
        f = link.receive_frame()
        if f is None:
            time.sleep(0.01)
            continue
        if skip_records and f.type == FrameType.Record:
            continue
        return f
    return None

cmd.send_status(link)
print(read_reply())

cmd.send_start(link)
print(read_reply())          # Ack

time.sleep(3)                 # let it record a few seconds
cmd.send_stop(link)
print(read_reply())          # Ack

cmd.send_replay(link, 10)
records = []
end = time.time() + 5
while time.time() < end:
    f = link.receive_frame()
    if f is None:
        time.sleep(0.005); continue
    if f.type == FrameType.Record:
        records.append(RecordDecoder.decode(f.payload))
    elif f.type == FrameType.Ack:
        break
print(f"got {len(records)} replayed records")

link.disconnect()
```

## Existing scripts (fixed-flow, non-interactive)

If a scripted run is preferred over the REPL: `groundstation/probe.py --port <PORT>` (STATUS + bad-cmd NACK + live capture) and `tests/hw/gate_phase5.py --port <PORT>` (full START/STOP/REPLAY/ERASE gate check). See their `--help` for flags.
