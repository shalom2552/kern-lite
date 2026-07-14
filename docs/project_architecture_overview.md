# KERN-LITE — Project Architecture Overview

> Top-down architectural reference for the KERN-LITE embedded black-box data logger.
> Scope: custom application logic only. STM32 HAL/LL, CMSIS, FatFs, and FreeRTOS
> kernel sources under `Drivers/`, `Middlewares/`, and `Core/` (CubeMX-generated
> boilerplate) are deliberately excluded except where they form the integration
> boundary with custom code.
>
> Target MCU: **STM32L476RG** (Cortex-M4F, 80 MHz SYSCLK from HSE 8 MHz → PLL).
> Languages: **C** (CubeMX glue), **C++17** (firmware application), **Python 3** (ground station).

### Canonical sources & authority

Three documents describe this system; they play distinct roles and are resolved
in this order on any conflict:

1. **`KERN-LITE_Project_Specification.pdf`** — *normative*. Defines *what* must be
   delivered: fixed protocol/record layouts, constants, requirements (`FR-*`,
   `NFR-*`), and acceptance criteria (`AC-*`). "Protocol and record layouts are
   fixed." **This is the tie-breaker.**
2. **`KERN-LITE_Complete_Student_Project_Handbook.pdf`** — *process*. Defines
   *how* the team gets there: Phase 0 setup, Days 1–7 tasks, daily gates. Its
   Phase-0 code listings are **stubs to be replaced** and must not be read as the
   final contract.
3. **This document + the codebase** — *implementation*. What the code actually does.

> **Stub-vs-final note.** The handbook's Phase-0 `frame.hpp` listing carries
> placeholder values that the final protocol supersedes — `RECORD = 0x11`,
> `kFrameOverhead = 8`, and a different `NackCode` numbering. The Specification
> (§8.2–8.4) and the shipped code agree on the **final** values used throughout
> this document: `RECORD = 0x10`, overhead **9**, `NackCode{CrcError=0x01 …
> BadMagic=0x06}`. The retired opcode `0x11` is precisely the old stub RECORD
> code — which is why `frame.hpp` marks `0x05/0x07/0x11` as retired.

### Central engineering theme — DATA SURVIVABILITY (spec §3.1)

Every architectural choice below serves one intent: *stored telemetry must
survive noise, corruption, and power loss.* Concretely — every stored record is
**independently checksummed** (record CRC, distinct from the transport frame
CRC), the ring **overwrites only the oldest retained data**, metadata is
**periodically persisted**, and the recorder **reconstructs its write head after
an unexpected reset**. Read the storage, protocol, and integrity sections as
different facets of that single requirement.

---

## 1. System-Level Overview

KERN-LITE is a three-tier telemetry logging system. Sensor data is acquired and
filtered on an MCU, persisted to an SD card as a crash-recoverable circular log,
streamed live over UART, and consumed/analyzed by a host-side Python ground station.

The system decomposes into **four macro-components**:

| # | Macro-Component | Language | Location | Responsibility |
|---|-----------------|----------|----------|----------------|
| A | **Flight/Embedded Recorder** (firmware application) | C++17 | `firmware/` | Sensor acquisition, DSP filtering, state machine, storage, command handling. Runs on FreeRTOS. |
| B | **Platform Glue / Boot** (CubeMX-generated) | C | `Core/`, `FATFS/Target/`, `Middlewares/` | HAL peripheral init, FreeRTOS kernel, FatFs disk I/O, boot hand-off into C++ app. |
| C | **Comms / Telemetry Protocol** (shared contract) | C++ ↔ Python | `firmware/protocol/`, `groundstation/frame.py`, `groundstation/crc.py` | Binary framing, CRC-32, wire layout. Dual implementation kept byte-for-byte compatible across both ends. |
| D | **Ground Station** (host analytics) | Python 3 | `groundstation/` | Serial link management, frame dispatch, telemetry aggregation, device state mirror, session recording, integrity checks. |

Plus a **cross-cutting test tier** (`tests/`): host-compiled C++ unit tests
(`tests/host/`) with FreeRTOS/HAL/FatFs stubs, pytest ground-station tests
(`tests/gs/`), cross-language wire-vector tests, and a hardware phase gate
(`tests/hw/gate_phase5.py`).

### 1.1 Macro-level data path

```
  [Physical sensors]                                    [Host PC]
        │                                                   │
        ▼                                                   ▼
  ┌───────────────── A: Recorder (STM32, C++/FreeRTOS) ──────────────┐
  │  Sensor task → DSP Channels → SensorRecord → SensorBus           │
  │        │                           │                             │
  │        │ (live)                    │ (persist)                   │
  │        ▼                           ▼                             │
  │   CommLink.send()            CircularLog (FatFs/SD)              │
  │        │                           ▲                             │
  │        │                           │ replay                      │
  │        ▼                           │                             │
  │   protocol::encode ──── UART ──────┴──── protocol::Decoder       │
  └────────────────────────────│──────────────────────────│─────────┘
                               UART2 @115200 (ST-Link VCOM)
                                            │
  ┌─────────────────── D: Ground Station (Python) ────────────────────┐
  │  SerialLink.receive_frame → Decoder → _dispatch:                   │
  │     RECORD → IntegrityChecker → TelemetryModel → Session          │
  │     STATUS → DeviceStateModel + StorageModel                      │
  │     NACK   → alert_log ;  ACK → close replay txn                  │
  │  CommandSender / StatusPoller → SerialLink.send_frame → UART      │
  └───────────────────────────────────────────────────────────────────┘
```

---

## 2. Inter-Component Communication

### 2.1 Physical & transport layer

- **Bus:** USART2, `115200` baud, 8N1, over the ST-Link Virtual COM Port
  (pins PA2/PA3, AF7). Baud is defined once as `kern::config::kUartBaud`
  (firmware) and defaulted to `115200` in `groundstation/link.py`.
- **Firmware side:** interrupt-driven single-byte RX (`HAL_UART_Receive_IT`),
  blocking TX (`HAL_UART_Transmit`, 100 ms timeout) serialized by a mutex.
- **Host side:** `pyserial` with a 50 ms read timeout, buffered-chunk reads
  (`ser.in_waiting`), background auto-reconnect thread.

### 2.2 Frame protocol (the shared contract, macro-component C)

Wire layout, little-endian, defined identically in `firmware/protocol/frame.hpp`
and `groundstation/frame.py`:

```
  ┌─────┬──────┬────────┬────────┬───────────┬──────────┬─────┐
  │ STX │ TYPE │ LEN_LO │ LEN_HI │  PAYLOAD  │  CRC32    │ ETX │
  │0xAB │ 1 B  │  1 B   │  1 B   │ 0..256 B  │  4 B LE   │0xCD │
  └─────┴──────┴────────┴────────┴───────────┴──────────┴─────┘
   Fixed overhead = 9 bytes (kFrameOverhead). Max frame = 9 + 256 = 265 B.
```

- **CRC-32 coverage:** `TYPE + LEN(2) + PAYLOAD`. STX/ETX are **not** covered.
- **CRC-32 algorithm (spec §11 — "CRC-32 / IEEE 802.3 / ITU-T V.42"):**

  | Parameter | Value |
  |-----------|-------|
  | Normal polynomial | `0x04C11DB7` |
  | Reflected polynomial | `0xEDB88320` |
  | Initial value | `0xFFFFFFFF` |
  | Input reflection | Yes |
  | Output reflection | Yes |
  | Final XOR | `0xFFFFFFFF` |
  | **Known-answer test** | `CRC32("123456789") == 0xCBF43926` |

  This is standard zlib CRC-32.
  - Firmware: `firmware/protocol/crc32.cpp`, a `constexpr` 256-entry table built
    at compile time; streaming API `crc32Begin/Update/Finalize` + one-shot `crc32`.
  - Host: `groundstation/crc.py` delegates to `zlib.crc32` (masked to 32-bit) —
    guaranteed equal to the firmware table implementation.
  - **Why the KAT is a hard gate:** both ends must independently reproduce
    `0xCBF43926` *before any other protocol work* (spec "DAY 1 BLOCKER"). A CRC
    mismatch here silently poisons every downstream frame and record, so it is
    caught first.
- **Framing state machine:** both ends implement the *identical* 10-state parser
  (`WaitStx → Type → LenLo → LenHi → Payload → Crc0..3 → WaitEtx`). Oversized
  `len > 256` resets to resync (`SyncError`). Garbage before STX is silently
  dropped. This state-for-state parity is an explicit design invariant and is
  verified by cross-vector tests.

### 2.3 Frame types & opcodes

| Opcode | Name | Direction | Payload |
|--------|------|-----------|---------|
| `0x01` | `CmdStart` | GS → Dev | empty |
| `0x02` | `CmdStop` | GS → Dev | empty |
| `0x03` | `CmdStatus` | GS → Dev | empty |
| `0x04` | `CmdReplay` | GS → Dev | `u16` count (LE), default 120 |
| `0x06` | `CmdErase` | GS → Dev | `u32` magic `0xDEADC0DE` (LE) |
| `0x10` | `Record` | Dev → GS | 32-byte `SensorRecord` |
| `0x12` | `Status` | Dev → GS | 14-byte status block |
| `0x20` | `Ack` | Dev → GS | empty |
| `0x21` | `Nack` | Dev → GS | `u8` `NackCode` |

Opcodes `0x05`, `0x07`, `0x11` are **retired** and must never be reused.

**NackCode:** `CrcError=1`, `BadCommand=2`, `InvalidState=3`, `StorageError=4`,
`BadMagic=6`.

### 2.4 Serialized data structures

**`SensorRecord` — 32 bytes, `#pragma pack(1)`** (record payload). Firmware
`firmware/storage/sensor_record.hpp` ↔ host `groundstation/telemetry.py`
(`_RECORD_FMT = "<IHHhhHHHBBB7xI"`):

```
  offset  type   field         scaling / meaning
  0       u32    timestamp     seconds (HAL tick / 1000)
  4       u16    ms            millisecond component
  6       u16    seq           per-record sequence (wraps at 65536)
  8       i16    lm35_c        LM35 temp ×10 °C
  10      i16    dht_temp_c    DHT11 temp ×10 °C
  12      u16    dht_hum       DHT11 humidity ×10 %
  14      u16    light         photodiode normalized ×65535
  16      u16    pot           potentiometer normalized ×65535
  18      u8     alert_bits    DSP threshold alert bitmask
  19      u8     state         FSM state (0/1/2)
  20      u8     fault_bits    sensor fault bitmask
  21      u8[7]  reserved      padding
  28      u32    crc32         CRC over bytes 0..27
```

> Note: firmware doc-comments describe LM35 as "×100" and light/pot as "×1000",
> but the actual code (`orchestrator.cpp`) and host decoder both use **×10** for
> temps and **×65535** for light/pot. Code is authoritative.

**STATUS payload — 14 bytes**. Firmware `command_handler.cpp::sendStatus()` ↔
host `groundstation/storage_panel.py` (`_STATUS_FMT = "<BBBBIIH"`):

```
  u8 state | u8 sd_mounted | u8 file_count | u8 current_file |
  u32 total_records | u32 wrap_count | u16 write_index/records_in_file
```

**`LogMeta` — 36 bytes, `#pragma pack(1)`** (on-SD only, not on the wire).
See §3.1.3.

### 2.5 Alert & fault bitmasks (packed in `SensorRecord`)

Kept in sync between `orchestrator.cpp`, `sensor_record.hpp`, and
`telemetry.py`/`state.py`:

| `alert_bits` | | `fault_bits` | |
|---|---|---|---|
| `0x01` LM35 high | `0x02` LM35 low | `0x01` LM35 range | `0x02` DHT timeout |
| `0x04` light high | `0x08` light low | `0x04` DHT bad data | `0x08` light stuck |
| `0x10` pot high | `0x20` pot low | `0x10` pot stuck | |
| `0x40` DHT temp high | `0x80` DHT hum high | | |

---

## 3. Component Deep Dive

### 3.A Flight/Embedded Recorder (`firmware/`)

C++17 application in namespace `kern::*`. No dynamic allocation (NFR-02): all
FreeRTOS objects are statically allocated (`xTaskCreateStatic`,
`xSemaphoreCreate*Static`). Layered as `hal · sensors · dsp · protocol · storage
· recorder · system`, with dependencies flowing strictly downward.

```
  system (Orchestrator, tasks, config, board, init)
     │  owns & wires everything below
     ├── recorder (StateMachine, SensorBus, CommLink, CommandHandler)
     ├── storage  (CircularLog, SensorRecord)
     ├── sensors  (Lm35, Photodiode, Potentiometer, Dht11, Buttons, RadiationLatch)
     ├── dsp      (Channel = MovingAverage + ThresholdDetector)
     ├── protocol (Frame, codec Decoder/encode, crc32)  ← shared with host
     └── hal      (adc, gpio, buzzer, watchdog — thin HAL wrappers)
```

#### 3.A.1 `system/` — orchestration & RTOS integration

- **`Orchestrator`** (`orchestrator.hpp/.cpp`): the application core, a Meyers
  singleton (`Orchestrator::instance()`). Owns *all* subsystem objects by value
  (state machine, sensor bus, circular log, comm link, command handler, five DSP
  channels, five sensor drivers). Exposes four task bodies — `runSensorTask`,
  `runStorageTask`, `runCommsTask`, `runSystemTask` — each an infinite
  `vTaskDelay`-paced loop. Detailed in §4.
- **`tasks.cpp`** (`kern_create_tasks`): allocates static TCBs + stacks, calls
  `Orchestrator::init()`, then spawns the four tasks. Also provides the
  FreeRTOS static-memory callbacks (`vApplicationGetIdleTaskMemory`,
  `...TimerTaskMemory`).
- **`init.cpp`** (`kern_boot`, `extern "C"`): boot shim → `kern_create_tasks()`.
- **`config.hpp`** (`kern::config`): all tunables — task periods, baud, DSP
  window size, per-sensor `ThresholdConfig`s, buzzer tones, ring geometry, erase
  magic.
- **`board.hpp`** (`kern::board`): `Pin{port,n}` constants and `AdcChannel` enum
  — the single source of pin/channel truth.
- **`write_failure_policy.hpp`** (`WriteFailurePolicy`): counts consecutive
  storage failures, trips at 3. Header-only, shared with host tests.

#### 3.A.2 `recorder/` — protocol-facing runtime

- **`StateMachine`** (`state_machine.hpp/.cpp`): 3-state FSM
  `Idle / Recording / Fault`. Pure transition table, no side effects. Events:
  `ChecksPassed, SdFault, UartStart, UartStop, ShortPress, FaultCleared`.
- **`SensorBus`** (`sensor_bus.hpp`, header-only): double-buffered
  single-slot mailbox for the latest `SensorRecord`, guarded by a static mutex
  with a 5 ms acquire timeout. Producer = Sensor task, consumer = Storage task.
- **`CommLink`** (`comm_link.hpp/.cpp`): UART transport. ISR-driven RX feeds a
  `protocol::Decoder`; `poll()` hands a completed frame to the caller; `send()`
  encodes+transmits under a mutex. See §4 for concurrency detail.
- **`CommandHandler`** (`command_handler.hpp/.cpp`): the command dispatcher.
  Binds `StateMachine` + `CircularLog`, validates each command against FSM state,
  performs storage actions, and emits ACK/NACK/STATUS/RECORD replies.

#### 3.A.3 `storage/` — crash-recoverable circular log

- **`CircularLog`** (`circular_log.hpp/.cpp`): a ring of `LOG_FILE_COUNT = 4`
  FatFs files (`LOG00.BIN`..`LOG03.BIN`), `RECORDS_PER_FILE = 256` → capacity
  1024 records. Each record `f_sync`'d immediately for crash safety.
  `LogMeta` (36 B, CRC-checked) persisted to `META.BIN` every
  `META_FLUSH_EVERY_N = 16` writes and on explicit flush.
  - **Recovery on mount:** if `META.BIN` valid, resume from saved head and scan
    forward for records newer than the last flushed one; if invalid/missing, do a
    full-capacity scan (`recoverPosition`) picking the newest record by
    `(timestamp, ms, seq)` ordering, inferring `wrap_count` from whether every
    slot is valid.
  - **Replay:** `replayNewest(n, cb, ctx)` walks the newest `n` slots
    oldest-first, invoking a callback per record; corrupt records are still
    delivered (flagged `Corrupt`) so the GS can report them.
  - **Erase:** `eraseAll(magic)` requires `0xDEADC0DE`, unlinks all files +
    meta, remounts fresh.
- **`SensorRecord`** (`sensor_record.hpp`): the 32-byte record + fault-bit
  constants. `static_assert`s lock size==32 and crc offset==28.

#### 3.A.4 `sensors/` — hardware drivers

| Driver | Interface | Notes |
|--------|-----------|-------|
| `Lm35`, `Photodiode`, `Potentiometer` | ADC1 (via `hal::adc`) | header-only, return °C or normalized [0,1]. |
| `Dht11` (`dht11.hpp/.cpp`) | bit-banged GPIO PB5 | DWT-based µs timing, critical-section 40-bit read, checksum verify. Slow cadence. |
| `Buttons` (`buttons.hpp`) | GPIO PA10 (SW1) | polled short/long-press FSM (short 30–1000 ms, long ≥1000 ms). |
| `RadiationLatch` (`radiation_latch.hpp/.cpp`) | EXTI3 (SW2/PB3) | ISR → `xSemaphoreGiveFromISR`; count-preserving consume. |

#### 3.A.5 `dsp/` — signal conditioning (header-only templates)

- **`MovingAverage<T,N>`**: fixed-window circular-buffer running mean, O(1)
  update, no heap.
- **`ThresholdDetector`**: 3-state (`Normal/LowAlert/HighAlert`) with hysteresis
  on the return-to-normal edge.
- **`Channel<N>`**: composes the two — `process(raw) → {raw, filtered, alert}`.
  Instantiated five times in the orchestrator (`kDspWindow = 16`).

#### 3.A.6 `hal/` — thin STM32 HAL wrappers

Header-only, stateless: `adc` (channel config + read + volts), `gpio`
(set/clear/toggle/read by `board::Pin`), `buzzer` (TIM3_CH1 PWM tone), `watchdog`
(IWDG refresh). These form the *only* sanctioned path to raw HAL from app code.

### 3.B Platform Glue / Boot (`Core/`, CubeMX)

CubeMX-generated C. The single integration seam into the C++ app is in
`Core/Src/freertos.c`: `MX_FREERTOS_Init()` → `kern_boot()` (USER CODE block) →
`kern_create_tasks()`. The generated `StartDefaultTask` is an idle
`osDelay(1)` loop; all real work runs in the four `kern::` tasks. Peripheral
handles (`huart2`, `hadc1`, `hiwdg`, `htim3`) are CubeMX globals referenced via
`extern` from the C++ layer. Per project convention, `.ioc`/generated peripheral
& NVIC config is edited only through the CubeMX GUI.

### 3.D Ground Station (`groundstation/`)

Python 3, package `groundstation`. Model-oriented: the transport layer
(`SerialLink`) owns references to a set of optional model objects and fans each
decoded frame out to them. Any model may be `None` (that dispatch stage is
skipped), which keeps the link independently testable.

```
  SerialLink ── decoder ──► Decoder (frame.py)
      │  holds refs to (any may be None):
      ├── state_model        → DeviceStateModel   (state.py)
      ├── storage_model      → StorageModel        (storage_panel.py)
      ├── telemetry_model    → TelemetryModel       (telemetry.py)
      ├── session            → Session              (session.py)
      ├── integrity_checker  → IntegrityChecker      (integrity.py)
      └── alert_log          → (host UI sink)

  CommandSender (commands.py) ── build/record/send ──► SerialLink
  StatusPoller  (commands.py) ── periodic CMD_STATUS ─► SerialLink
  probe.py ── standalone CLI harness for real-board bring-up
```

Modules covered per-file in §4.

---

## 4. File-Level Mapping

Custom files only. Each entry: purpose · core types · concurrency · I/O.

### Firmware — `firmware/protocol/`

| File | Purpose | Core types | Concurrency | I/O |
|------|---------|-----------|-------------|-----|
| `frame.hpp` | Wire constants & structs | `FrameType`, `NackCode`, `Frame{type,payload[256],len}` | — | — |
| `codec.hpp/.cpp` | Frame encode + streaming decode FSM | `encode()`, `Decoder` (10-state), `DecodeResult` | none (per-instance) | byte streams |
| `crc32.hpp/.cpp` | CRC-32 (0xEDB88320) | `constexpr` table, `crc32/Begin/Update/Finalize` | pure | — |

### Firmware — `firmware/recorder/`

| File | Purpose | Core types | Concurrency | Sockets/HW |
|------|---------|-----------|-------------|------------|
| `comm_link.hpp/.cpp` | UART transport | `CommLink`; global `g_comm_link` | **mutex** `m_mutex` (TX serialize); `volatile m_frame_ready`; `__disable_irq/__enable_irq` in `poll()`; `friend HAL_UART_RxCpltCallback` runs in ISR | USART2 (`huart2`), IT RX + blocking TX |
| `command_handler.hpp/.cpp` | Command dispatch & reply | `CommandHandler` | none directly (calls into log/link) | via `g_comm_link` |
| `state_machine.hpp/.cpp` | Recorder FSM | `StateMachine`, `State`, `Event` | none (single-writer) | — |
| `sensor_bus.hpp` | Latest-record mailbox | `SensorBus` | **static mutex**, 5 ms timeout | — |

`CommandHandler::dispatch` guards: `CmdStart` needs Idle → Recording + STATUS +
ACK; `CmdStop` needs Recording → Idle + `flushMeta` + STATUS + ACK; `CmdStatus`
→ STATUS; `CmdReplay` needs Idle + mounted, streams RECORD frames via
`replayRecord` callback; `CmdErase` needs Idle + 4-byte magic; unknown →
NACK `BadCommand`.

### Firmware — `firmware/storage/`

| File | Purpose | Core types | Concurrency | I/O |
|------|---------|-----------|-------------|-----|
| `circular_log.hpp/.cpp` | 4-file ring log, meta persistence, recovery, replay | `CircularLog`, `LogMeta`(36 B), `StorageStatus`, `RecordCb` | single-owner (Storage task); FatFs mutex is FatFs-internal | FatFs `f_open/read/write/lseek/sync/unlink`, SD via SPI1 |
| `sensor_record.hpp` | 32-B record + fault bits | `SensorRecord` | — | — |

### Firmware — `firmware/system/`

| File | Purpose | Core types | Concurrency |
|------|---------|-----------|-------------|
| `orchestrator.hpp/.cpp` | App core; 4 task bodies; sensor→DSP→record assembly; storage/fault mgmt; LEDs/buzzer/button/heartbeat | `Orchestrator` (singleton) | owns objects touched by 4 tasks; coordinates via `SensorBus` mutex & `CommLink` |
| `tasks.cpp` / `tasks.hpp` / `tasks_defs.hpp` | Static task creation; stack/prio constants | `kern_create_tasks`, `kern::tasks::*` | `xTaskCreateStatic`, static TCBs/stacks |
| `init.cpp/.hpp` | `kern_boot` boot shim | `extern "C" kern_boot` | — |
| `config.hpp` | Tunables | `kern::config::*` | — |
| `board.hpp` | Pins + ADC channels | `board::Pin`, `AdcChannel` | — |
| `write_failure_policy.hpp` | Consecutive-failure trip (≥3) | `WriteFailurePolicy` | — |

**Task table** (from `tasks_defs.hpp` / `config.hpp`):

| Task | Body | Period | Prio | Stack (words) | Role |
|------|------|--------|------|---------------|------|
| Sensor | `runSensorTask` | 100 ms | idle+2 | 512 | sample → DSP → assemble record → publish + live-stream (only while Recording) |
| Storage | `runStorageTask` | 100 ms | idle+2 | 768 | mount/ensure, write latest once/seq, fault recovery + remount |
| Comms | `runCommsTask` | 10 ms | idle+3 (highest) | 384 | poll `CommLink` → `CommandHandler::dispatch` |
| System | `runSystemTask` | 50 ms | idle+1 (lowest) | 384 | watchdog kick, state LEDs, buzzer tones, SW1 short-press, 5 s STATUS heartbeat |

**Concurrency map (firmware):**
- **Sensor ↔ Storage:** decoupled through `SensorBus` (mutex, single-slot);
  Storage stores a record exactly once by comparing `seq` vs `m_lastStoredSeq`.
- **ISR ↔ Comms:** `HAL_UART_RxCpltCallback` (ISR) → `CommLink::feed` sets
  `volatile m_frame_ready`; Comms task `poll()` copies under `__disable_irq`.
- **EXTI ISR ↔ tasks:** `RadiationLatch::isr` → binary semaphore give-from-ISR.
- **TX serialization:** every `CommLink::send` (from Sensor live-stream, Comms
  replies, System heartbeat) is serialized by `m_mutex`.
- **Fault escalation:** `WriteFailurePolicy` trips `Event::SdFault` after 3
  consecutive write/mount failures; in Fault the Storage task retries `remount`,
  and after 3 failed remounts issues `NVIC_SystemReset()`.

### Ground Station — `groundstation/`

| File | Purpose | Core classes | Concurrency | Sockets/FS |
|------|---------|--------------|-------------|------------|
| `frame.py` | Framing/codec (host mirror of firmware) | `Frame`, `FrameType`, `NackCode`, `encode()`, `Decoder`, `CrcError/SyncError` | — | — |
| `crc.py` | CRC-32 via `zlib` | `crc32`, `crc32_update` | — | — |
| `link.py` | Serial transport + frame fan-out | `SerialLink` | **`threading.Thread`** auto-reconnect (daemon, 2 s poll); `deque` RX queue; tracks rx/tx/crc/sync/nack counters, latency window | **`serial.Serial`** (pyserial), 50 ms timeout |
| `commands.py` | Command builders + poller | `CommandSender`, `StatusPoller(threading.Thread)` | `StatusPoller` daemon thread, 5 s interval, `Event` stop | via `SerialLink` |
| `telemetry.py` | Record decode + running stats | `SensorRecord`, `RecordDecoder`, `TelemetryModel`, `_ChannelRunning` (Welford mean, alert-duration) | — | — |
| `state.py` | Device FSM mirror + command gating | `DeviceStateModel`, `Transition` | — | consumes STATUS |
| `storage_panel.py` | Ring/storage view from STATUS | `StorageModel`, `ring_visual()`, live/replay counters | — | consumes STATUS |
| `session.py` | On-disk session recorder/loader | `Session` | flush every 16 records | writes `session.bin` (32 B record + f64 wall time) + `frames.log`; `Session.load()` |
| `integrity.py` | Record-CRC recheck + seq-gap detection | `IntegrityChecker` | — | logs `STORAGE_CORRUPTION_WARNING` / `SEQ_GAP` |
| `probe.py` | Standalone real-board CLI (STATUS, NACK test, RECORD capture, counters) | `main()`, `capture_records()` | uses `SerialLink` | argparse CLI, serial |
| `__init__.py` | Package marker | — | — | — |

**`SerialLink._dispatch` routing (the host-side heart):**
- `RECORD` → `IntegrityChecker.check_frame` (record CRC) → `RecordDecoder.decode`
  → `check_sequence` → `TelemetryModel.ingest` → `Session.append_record` →
  `StorageModel.note_live_record` **or** `note_replay_record` (replay window is
  open between `CmdReplay` send and its `ACK`, tracked by `_in_replay`).
- `STATUS` → `DeviceStateModel.update_from_status` + `StorageModel.update_from_status`.
- `NACK` → decode `NackCode` → `alert_log.add`.
- `ACK` → closes any in-flight replay transaction.

### Tests (`tests/`)

- `tests/host/` — C++ host unit tests (`test_codec`, `test_cross_vectors`,
  `test_dsp`, `test_fsm`, `test_storage`) built with stubs in
  `tests/host/stubs/` (FreeRTOS, semphr, HAL) and a FatFs shim
  (`tests/host/fatfs_shim/`). Driven by `tests/Makefile` / `Makefile.ci`.
- `tests/gs/` — pytest for every ground-station module + `test_cross_vectors.py`
  (byte-level parity with firmware) + `test_status_poller.py`.
- `tests/hw/gate_phase5.py` — on-hardware phase-5 acceptance gate.
- `conftest.py` — pytest path/fixture setup at repo root.

---

## 5. Data Flow & State Lifecycles

### 5.1 Live telemetry: sensor → C → C++ → UART → Python

```
 (1) Sensor task (100 ms, only while Recording):
       Lm35/Photodiode/Potentiometer.read*  ── hal::adc ──► raw ADC (12-bit)
       Dht11.read (every 20th tick, ~2 s)
             │  each channel:
             ▼
     dsp::Channel.process → MovingAverage(16) → ThresholdDetector(hysteresis)
             │  → {filtered value, alert state}
             ▼
     Orchestrator::assembleRecord:
        scale filtered → SensorRecord fields (×10 temps, ×65535 light/pot)
        pack alert_bits + fault_bits + state + seq + timestamp/ms
        crc32 over bytes 0..27  → record.crc32
             │
             ├──► SensorBus.publish(rec)         (→ Storage task, §5.2)
             └──► Orchestrator::streamRecord(rec)
                     └─ protocol::encode(RECORD frame) ─ CommLink.send (mutex)
                            └─ HAL_UART_Transmit ── UART ──►
 (2) Host SerialLink.receive_frame:
        pyserial read → Decoder.feed (per byte) → Frame(RECORD)
             │  frame CRC verified inside decoder
             ▼
        _dispatch_record:
           IntegrityChecker.check_frame  (re-verify record-level CRC 0..27)
           RecordDecoder.decode          (→ typed SensorRecord)
           IntegrityChecker.check_sequence(record, last_seq)  (16-bit wrap-aware gap)
           TelemetryModel.ingest         (min/max/Welford mean, alert durations)
           Session.append_record         (session.bin + wall time, flush/16)
           StorageModel.note_live_record
```

### 5.2 Persistence & replay

```
 Storage task (100 ms):
   if Fault:      recoverFromFault → CircularLog.remount → (ok) FaultCleared
                                                          → (3× fail) NVIC_SystemReset
   elif Recording && ensureMounted():
        rec = SensorBus.latest()
        if rec.seq != m_lastStoredSeq:
            CircularLog.writeRecord(rec):
                stamp record CRC → f_lseek(current_file, write_index*32)
                → f_write → f_sync (crash-safe) → advanceHead
                → every 16 records: writeMeta() (META.BIN, CRC-checked)
        on write/mount failure: WriteFailurePolicy.recordFailure → SdFault @3

 Replay (host-initiated):
   GS CmdReplay(n) ─► CommandHandler: Idle+mounted guard
        CircularLog.replayNewest(n, replayRecord):
            walk newest n slots oldest-first → encode each as RECORD frame → send
        ACK terminates the batch; GS StorageModel counts these as replay records.
```

### 5.3 Command / state lifecycle

Firmware FSM (`kern::recorder::StateMachine`) and its host mirror
(`DeviceStateModel`) track the same three states. The host `command_allowed()`
rules mirror the firmware `dispatch()` guards exactly:

```
        ┌──────────────────────────────────────────────┐
        │                                              ▼
     ┌──────┐  UartStart          ┌───────────┐  SdFault   ┌───────┐
     │ Idle │ ───────────────────►│ Recording │ ─────────► │ Fault │
     │      │ ◄─────────────────── │           │            │       │
     └──────┘  UartStop / ShortPress└───────────┘            └───────┘
        ▲            SdFault ──────────────────► Fault          │
        │                                                       │
        └───────────────── (Fault: FaultCleared → Recording) ◄──┘

  Command legality (both ends):
    START  : Idle only            STOP   : Recording only
    STATUS : always               REPLAY : Idle AND sd_mounted
    ERASE  : Idle only (+magic)
```

- **Device → host state sync:** every command reply and the 5 s heartbeat emit a
  STATUS frame; `DeviceStateModel.update_from_status` detects state changes and
  logs `Transition{wall_time, session_seq, from, to, duration_in_prev}`.
- **Reboot detection:** `StatusPoller.handle_status_reply` flags
  `REBOOT_DETECTED` when `total_records` drops by >50% between polls.
- **Integrity signals:** `IntegrityChecker` emits `STORAGE_CORRUPTION_WARNING`
  (record CRC fail) and `SEQ_GAP size=N` (sequence discontinuity); `NACK` frames
  are surfaced to the alert log with their decoded `NackCode`.

### 5.4 Boot lifecycle

```
  Reset → CubeMX MX_*_Init (clocks, GPIO, ADC1, SPI1, USART2, TIM3, IWDG, FatFs)
        → MX_FREERTOS_Init → kern_boot() → kern_create_tasks():
              Orchestrator::init()  (SensorBus/CommLink/Buttons init, handler.bind)
              create Sensor/Storage/Comms/System static tasks
        → vTaskStartScheduler → tasks run; StartDefaultTask idles.
```

---

## Appendix — Key invariants for downstream tooling

- **Wire/record parity:** `firmware/protocol/*` ≡ `groundstation/frame.py`+`crc.py`;
  `SensorRecord` layout ≡ `telemetry.py::_RECORD_FMT`; STATUS ≡
  `storage_panel.py::_STATUS_FMT`. Enforced by `test_cross_vectors` on both sides.
- **Sizes:** frame overhead 9 B; max payload 256 B; `SensorRecord` 32 B
  (CRC @28); `LogMeta` 36 B (CRC @32); STATUS 14 B.
- **Ring geometry:** 4 files × 256 records = 1024-record capacity; meta flush
  every 16 writes; erase magic `0xDEADC0DE`.
- **Timing:** Sensor/Storage 100 ms, Comms 10 ms, System 50 ms; DHT every ~2 s;
  STATUS heartbeat 5 s; DSP window 16; fault trip at 3 consecutive failures.
```
