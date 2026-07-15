# Ground Station API — Dashboard Developer Guide

How to use the `groundstation/` package to build a dashboard (GUI or web).
You do **not** need to touch the protocol internals — the package already handles
framing, CRC, decoding, and dispatching. Your dashboard only needs to:

1. Wire the models together (a few constructors).
2. Run a receive loop that calls `link.receive_frame()` repeatedly.
3. Read the models' public attributes to draw the UI.
4. Call `CommandSender` methods when the user clicks buttons.

A complete, working example of all of this wiring already exists:
**`groundstation/probe.py`** (class `GateProbe.__init__` and `_process_one`).
Copy its structure.

---

## 1. The files, by role

| File | What it gives the dashboard |
|---|---|
| `link.py` | `SerialLink` — the connection. Owns the serial port, decodes frames, auto-reconnects, and **pushes data into all the models for you**. |
| `commands.py` | `CommandSender` — send START / STOP / STATUS / REPLAY / ERASE. `StatusPoller` — background thread that polls STATUS every 5 s. |
| `telemetry.py` | `SensorRecord` — one decoded sensor sample (the main data object). `TelemetryModel` — running min/max/mean per channel. Channel names, alert masks. |
| `state.py` | `DeviceStateModel` — current device state (Idle/Recording/Fault), transition history, and `command_allowed()` for enabling/disabling buttons. |
| `storage_panel.py` | `StorageModel` — SD-card ring state from STATUS frames, plus `ring_visual()` which returns ready-to-draw dicts. |
| `chart.py` | `RollingChart` — rolling window of last 120 records; `channel_series()` returns plot-ready arrays; `render()` draws onto matplotlib axes. |
| `stats.py` | `SessionStats` — per-channel n/min/max/mean/stddev/alert stats (richer than TelemetryModel; you must feed it yourself). |
| `timeline.py` | `StateTimeline` — state bands + alert/reboot events for a timeline widget. Feed it yourself. |
| `alert_log.py` | `AlertLog` — one time-ordered event list (NACKs, alerts, CRC errors, reboots…) for an "events" panel. |
| `link_quality.py` | `LinkQualityMonitor` — 0–100 % link quality score, heartbeat-loss and reboot detection. Feed it yourself. |
| `session.py` | `Session` — records everything to `sessions/<timestamp>/` on disk; `Session.load()` re-opens an old session for offline viewing. |
| `export.py` | `session_to_csv()`, `alert_log_to_text()`, `timeline_to_text()`, `raw_frame_log_to_text()` — "Export" buttons. |
| `frame.py` | `Frame`, `FrameType`, `NackCode` — protocol types. You only need `FrameType` (to check `frame.type`) and `NackCode` (to name errors). |
| `integrity.py` | `IntegrityChecker` — record CRC + sequence-gap checks. Just construct it and hand it to `SerialLink`. |
| `crc.py` | Internal CRC math. Never used directly. |
| `probe.py` | Not part of the API — a CLI test tool, but the **best reference** for how everything wires together. |

---

## 2. Wiring it up

```python
from groundstation.alert_log import AlertLog
from groundstation.chart import RollingChart
from groundstation.commands import CommandSender, StatusPoller
from groundstation.integrity import IntegrityChecker
from groundstation.link import SerialLink
from groundstation.link_quality import LinkQualityMonitor
from groundstation.session import Session
from groundstation.state import DeviceStateModel
from groundstation.stats import SessionStats
from groundstation.storage_panel import StorageModel
from groundstation.telemetry import TelemetryModel
from groundstation.timeline import StateTimeline

alert_log = AlertLog()
state     = DeviceStateModel()
storage   = StorageModel()
telemetry = TelemetryModel()
session   = Session()                 # writes to sessions/<timestamp>/

link = SerialLink(
    state_model=state,
    storage_model=storage,
    telemetry_model=telemetry,
    session=session,
    integrity_checker=IntegrityChecker(),
    alert_log=alert_log,
)

commands = CommandSender()
monitor  = LinkQualityMonitor(alert_log=alert_log)
chart    = RollingChart()             # capacity=120 records by default
stats    = SessionStats()
timeline = StateTimeline()
```

Connect:

```python
session.on_connect("/dev/ttyACM0")    # opens session files on disk
link.connect("/dev/ttyACM0", 115200)  # opens port + starts auto-reconnect thread
```

Disconnect: `link.disconnect()` then `session.close()`.

---

## 3. The receive loop (heart of the dashboard)

Call this repeatedly — from a background thread, a Qt/Tk timer (~every 10–50 ms),
or an asyncio task. `receive_frame()` is non-blocking (returns `None` when
nothing arrived).

```python
import time
from groundstation.frame import FrameType
from groundstation.telemetry import RecordDecoder

def poll_once():
    frame = link.receive_frame()      # decodes + auto-updates state/storage/
    now = time.time()                 # telemetry/session/alert_log for you
    monitor.update(now)               # heartbeat + periodic score recompute

    if frame is None:
        return

    monitor.on_frame(now)

    if frame.type == FrameType.Record:
        rec = RecordDecoder.decode(frame.payload)
        chart.update(rec)             # models NOT auto-fed by SerialLink:
        stats.ingest(rec, now)        # chart, stats, timeline, monitor
    elif frame.type == FrameType.Status:
        monitor.on_status(storage.total_records, now)
    elif frame.type == FrameType.Nack:
        monitor.on_nack()
```

Key point: `SerialLink` **automatically** feeds `state`, `storage`, `telemetry`,
`session`, `integrity`, `alert_log` (that's what the constructor wiring does).
You only manually feed `chart`, `stats`, `timeline`, `monitor`.

For state-transition markers on the chart/timeline, watch
`state.transitions` for new entries after each STATUS frame
(see `probe.py:_sync_transitions` for the pattern).

---

## 4. Sending commands (buttons)

```python
commands.send_start(link)             # begin recording
commands.send_stop(link)              # stop recording
commands.send_status(link)            # request STATUS
commands.send_replay(link, n=100)     # replay last n stored records
commands.send_erase(link, magic=...)  # erase storage (magic value from spec)
monitor.on_command()                  # tell quality monitor a command went out
```

Enable/disable buttons with the gating rules:

```python
state.command_allowed(FrameType.CmdStart)   # True only in Idle
state.command_allowed(FrameType.CmdStop)    # True only in Recording
state.command_allowed(FrameType.CmdReplay)  # Idle AND SD mounted
```

Optional: `StatusPoller(link, commands, state, storage)` is a daemon thread
that sends STATUS every 5 s so you don't have to (`.start()` / `.stop()`).

---

## 5. What to read for each dashboard panel

### Live values (current sample)
Latest record: `telemetry.records[-1]` (a `SensorRecord`). Display-unit properties:

| Property | Meaning | Unit |
|---|---|---|
| `rec.lm35_celsius` | LM35 temperature | °C |
| `rec.dht_temp_celsius` | DHT temperature | °C |
| `rec.dht_humidity` | DHT humidity | % |
| `rec.light_normalized` | Light | 0.0–1.0 |
| `rec.pot_normalized` | Potentiometer | 0.0–1.0 |
| `rec.seq` | Sequence number | — |
| `rec.alert_bits`, `rec.fault_bits` | Bitmasks (masks in `telemetry.py`) | — |
| `rec.state` | Device state at capture time | 0/1/2 |

`telemetry.channel_values(rec)` gives all five as a dict keyed by
`CHANNELS = ("lm35", "dht_temp", "dht_hum", "light", "pot")`.

### Device state panel
- `state.state` (0=Idle, 1=Recording, 2=Fault), pretty name via
  `DeviceStateModel.state_name(state.state)`
- `state.sd_mounted`
- `state.transitions` — list of `Transition(wall_time, from_state, to_state, duration_in_prev, …)`

### Storage / SD ring panel
- `storage.total_records`, `storage.wrap_count`, `storage.current_file`,
  `storage.records_in_file`, `storage.sd_mounted`
- `storage.ring_visual()` → list of `{"index", "is_current", "is_wrapped", "record_count"}` — draw directly
- `storage.live_record_count` / `storage.replay_record_count`

### Live chart
- `chart.channel_series("lm35")` → `{"seq": [...], "values": [...], "alert": [bool...], "lo": 10.0, "hi": 40.0}` — plot-ready with any library
- Or matplotlib directly: `chart.render({"lm35": ax1, "dht_temp": ax2, ...})`
- `chart.toggle_channel(name)` for show/hide checkboxes
- Markers: `chart.state_marker(transition)`, `chart.reboot_marker(seq)`, `chart.gap_notch(seq, gap)`

### Statistics panel
For each `name` in `CHANNELS`: `ch = stats.channels[name]` →
`ch.n`, `ch.min_val`/`ch.min_seq`, `ch.max_val`/`ch.max_seq`, `ch.mean`,
`ch.stddev`, `ch.alert_activations`, `ch.time_in_alert_s`, `ch.pct_in_alert`.

(`telemetry.channels[name]` has a simpler min/max/mean version if you skip `SessionStats`.)

### Link / connection panel
- `link.connection_state` — `"connected" | "reconnecting" | "disconnected"`
- `link.rx_count`, `link.tx_count`, `link.crc_error_count`,
  `link.sync_error_count`, `link.nack_count`, `link.nack_rate`
- `link.last_latency_ms`, `link.rolling_avg_latency_ms`
- `monitor.quality_pct` (0–100), `monitor.degraded` (<70 %), `monitor.poor` (<40 %),
  `monitor.reboot_count`

### Events / alerts panel
- `alert_log.entries` — list of `LogEntry(category, wall_time, session_seq, message)`
- `alert_log.filter({"NACK", "ALERT_ACTIVE"})` for category filters
- Categories: ALERT_ACTIVE, ALERT_CLEAR, STATE_TRANSITION, NACK, CRC_ERROR,
  SYNC_ERROR, SEQ_GAP, REBOOT, HEARTBEAT_TIMEOUT, GS_EVENT

### Timeline widget
- `timeline.segments` — dicts with `state`, `start_wall`, `end_wall`, `duration_s`,
  `start_seq`, `end_seq`, `record_count` (open segment has `end_wall=None`)
- `timeline.alerts`, `timeline.reboots`

### Export buttons
```python
from groundstation.export import (session_to_csv, alert_log_to_text,
                                  timeline_to_text, raw_frame_log_to_text)
session_to_csv(session, "out.csv")
alert_log_to_text(alert_log, "alerts.txt")
timeline_to_text(timeline, "timeline.txt")
raw_frame_log_to_text(session, "frames.txt")
```

### Offline / replay of past sessions
```python
old = Session.load("sessions/2026-07-14_10-30-00")   # dir or session.bin path
old.records      # list[SensorRecord]
old.wall_times   # list[float], parallel to records
```
Feed those into `RollingChart` / `SessionStats` to view a past session without hardware.

---

## 6. Threading notes

- `SerialLink.connect()` starts a daemon auto-reconnect thread; you never manage
  reconnection yourself. Watch `link.connection_state` to show the status.
- `receive_frame()` and `send_frame()` are meant to be called from **one** thread
  (your poll loop). Send commands from that same thread, or from the UI thread
  only if the poll loop runs there too (Qt/Tk timer approach — simplest).
- `StatusPoller` sends from its own thread; that is acceptable because writes
  are small, but the simplest safe design is: no `StatusPoller`, and your poll
  loop sends STATUS every 5 s itself (like `probe.py:capture` does).
