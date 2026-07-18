<div align="center">

![tests](https://github.com/shalom2552/kern-lite/actions/workflows/tests.yml/badge.svg)
![C++](https://img.shields.io/badge/C%2B%2B-17-00599C)
![Python](https://img.shields.io/badge/Python-3-3776AB)
![MCU](https://img.shields.io/badge/MCU-STM32L476RG-03234B)
![RTOS](https://img.shields.io/badge/RTOS-FreeRTOS-6cc24a)

</div>

# KERN-LITE

Fault aware black box data logger on an STM32L476RG (NUCLEO-L476RG) with a Python ground station.

Samples five sensor channels at 10 Hz, filters them, and writes CRC protected 32
byte records to a circular log on SD. Live telemetry streams over UART to a
Python dashboard with charts, stats, replay and exports. Records survive power
loss: each carries its own CRC and the write head is rebuilt after reset.

<div align="center">
<table>
  <tr>
    <th colspan="2">Ground station console</th>
  </tr>
  <tr>
    <td colspan="2"><img src="docs/images/Dashboard_live.png" alt="Ground station dashboard during a live recording session"></td>
  </tr>
  <tr>
    <td><img src="docs/images/Dashboard_graphs.png" alt="Rolling charts, all five channels"></td>
    <td><img src="docs/images/Dashboard_timeline.png" alt="State timeline and events"></td>
  </tr>
</table>
</div>

## Status


<details>
<summary>All 8 phases complete</summary>

- [x] Phase 0: project setup, RTOS smoke test
- [x] Phase 1: CRC-32 and frame codec
- [x] Phase 2: UART round trip (STATUS/ACK)
- [x] Phase 3: sensors, DSP, live SensorRecord stream
- [x] Phase 4: circular file storage, replay, recovery
- [x] Phase 5: state machine, full command set
- [x] Phase 6: ground station analytics
- [x] Phase 7: fault injection, validation, demo

</details>


## Architecture

Full deep-dive: [`docs/project_architecture_overview.md`](docs/project_architecture_overview.md).

Four macro-components, one shared wire contract:

| Component | Language | Location | Responsibility |
|---|---|---|---|
| Flight/Embedded Recorder | C++17 | `firmware/` | Sensor acquisition, DSP, FSM, storage, command handling. FreeRTOS. |
| Platform Glue / Boot | C | `Core/`, `Middlewares/` | CubeMX HAL init, FreeRTOS kernel, FatFs disk I/O, boot hand-off into C++. |
| Comms / Telemetry Protocol | C++ ↔ Python | `firmware/protocol/`, `groundstation/frame.py`, `groundstation/crc.py` | Binary framing + CRC-32, kept byte-for-byte identical on both ends. |
| Ground Station | Python 3 | `groundstation/` | Serial link, frame dispatch, telemetry aggregation, device-state mirror, session recording, integrity checks. |

```
[Sensors] → Sensor task → DSP(Channel) → SensorRecord → SensorBus
                                              │                │
                                       (live) │                │ (persist)
                                              ▼                ▼
                                        CommLink.send()   CircularLog (FatFs/SD)
                                              │                ▲ replay
                                              ▼                │
                                   protocol::encode ── UART ── protocol::Decoder
                                                    │
                        ┌───────────────────────────┴──────────────────────┐
                        │  GS: SerialLink.receive_frame → Decoder → dispatch │
                        │    RECORD → IntegrityChecker → TelemetryModel     │
                        │            → Session → StorageModel               │
                        │    STATUS → DeviceStateModel + StorageModel       │
                        │    NACK → alert_log ; ACK → close replay txn      │
                        └────────────────────────────────────────────────────┘
```

---

## Python Environment & Usage

The Ground Station and Dashboard run in an isolated Python virtual environment (`.venv`).
> **Windows:** Replace `.venv/bin/` with `.venv\Scripts\` in the commands below.

```bash
# Ubuntu/Debian/WSL prerequisites (install Tkinter):
sudo apt update && sudo apt install python3-tk

# First-time setup:
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Launch Dashboard / Simulator:
.venv/bin/python -m dashboard
.venv/bin/python -m dashboard.sim # No hardware simulator

# Development & Testing:
.venv/bin/pytest -v # Run tests
.venv/bin/python <path/to/file.py> # Run a Python file
.venv/bin/python3 -m py_compile <path-to-file> && echo OK || echo FAIL # Check Python syntax
```

Run all commands from the repo root.

## Build & Flash (firmware)

- **STM32CubeIDE:** import the repo root as an existing project, build the `Debug`
  configuration, flash with Run → Debug (ST-Link on the Nucleo).
- **CLI (CI parity):** `make -f tests/Makefile.ci firmware` (needs `gcc-arm-none-eabi`).

## Tests

```bash
make -C tests run     # host C++ tests (codec, DSP, storage, FSM, cross-vectors) + pytest
.venv/bin/pytest -v   # Python tests only
```

CRC known-answer on both ends: `CRC32("123456789") = 0xCBF43926`.

## Protocol

```
┌─────┬──────┬────────┬────────┬───────────┬──────────┬─────┐
│ STX │ TYPE │ LEN_LO │ LEN_HI │  PAYLOAD  │  CRC32   │ ETX │
│0xAB │ 1 B  │  1 B   │  1 B   │ 0..256 B  │  4 B LE  │0xCD │
└─────┴──────┴────────┴────────┴───────────┴──────────┴─────┘
 Fixed overhead = 9 bytes. Max frame = 265 B. CRC covers TYPE+LEN+PAYLOAD only.
```

| Opcode | Name | Direction | Payload |
|---|---|---|---|
| `0x01` | CmdStart | GS→Dev | empty |
| `0x02` | CmdStop | GS→Dev | empty |
| `0x03` | CmdStatus | GS→Dev | empty |
| `0x04` | CmdReplay | GS→Dev | `u16` count LE, default 120 |
| `0x06` | CmdErase | GS→Dev | `u32` magic LE = `0xDEADC0DE` |
| `0x10` | Record | Dev→GS | 32-byte `SensorRecord` |
| `0x12` | Status | Dev→GS | 14-byte status block |
| `0x20` | Ack | Dev→GS | empty |
| `0x21` | Nack | Dev→GS | `u8` NackCode |

`0x05`, `0x07`, `0x11` are retired, never reused. NackCode:
`CrcError=1, BadCommand=2, InvalidState=3, StorageError=4, BadMagic=6`.

**Command legality:** `START`/`ERASE` — Idle only · `STOP` — Recording only ·
`STATUS` — always · `REPLAY` — Idle **and** `sd_mounted`. Enforced on both
ends: firmware `CommandHandler::dispatch()`, GS `DeviceStateModel.command_allowed()`.

## Data structures

`SensorRecord` — 32 B, `#pragma pack(1)`, CRC over bytes 0–27:

```
offset  type   field         scaling
0       u32    timestamp     seconds
4       u16    ms            millisecond component
6       u16    seq           wraps at 65536
8       i16    lm35_c        LM35 temp ×10 °C
10      i16    dht_temp_c    DHT11 temp ×10 °C
12      u16    dht_hum       DHT11 humidity ×10 %
14      u16    light         photodiode normalized ×65535
16      u16    pot           potentiometer normalized ×65535
18      u8     alert_bits    DSP threshold alert bitmask
19      u8     state         FSM state (0/1/2)
20      u8     fault_bits    sensor fault bitmask
21      u8[7]  reserved
28      u32    crc32         over bytes 0..27
```

STATUS payload — 14 B: `u8 state | u8 sd_mounted | u8 file_count |
u8 current_file | u32 total_records | u32 wrap_count | u16 write_index`.

`LogMeta` (on-SD only, not on the wire) — 36 B, CRC over bytes 0–31.
Full byte-offset table: [`docs/design_note.md`](docs/design_note.md).

## State machine

```
        ┌──────────────────────────────────────────┐
        │                                          ▼
     ┌──────┐   UartStart        ┌───────────┐  SdFault   ┌───────┐
     │ Idle │ ──────────────────►│ Recording │───────────►│ Fault │
     │      │◄───────────────────│           │            │       │
     └──────┘ UartStop/ShortPress└───────────┘            └───────┘
        ▲                                                     │
        └────────────── FaultCleared → Recording ─────────────┘
```

## Tasks (firmware)

| Task | Period | Priority | Stack | Role |
|---|---|---|---|---|
| Sensor | 100 ms | idle+2 | 512 | sample → DSP → assemble record → publish + live-stream (Recording only) |
| Storage | 100 ms | idle+2 | 768 | mount/ensure, write once per seq, fault recovery + remount |
| Comms | 10 ms | idle+3 (highest) | 384 | poll `CommLink` → `CommandHandler::dispatch` |
| System | 50 ms | idle+1 (lowest) | 384 | watchdog kick, state LEDs, buzzer, SW1 short-press, 5 s STATUS heartbeat |

## Configured constants

| Constant | Value |
|---|---|
| `LOG_FILE_COUNT` | 4 |
| `RECORDS_PER_FILE` | 256 |
| Ring capacity | 1024 records (~102.4 s per wrap at 10 Hz) |
| `META_FLUSH_EVERY_N` | 16 |
| Sample rate | 10 Hz |
| DSP window | 16 |
| UART | 115200 baud, USART2 |
| `ERASE_MAGIC` | `0xDEADC0DE` |
| Max consecutive write/mount failures | 3 (`kern::config::kMaxWriteFails`) |
| STATUS heartbeat | 5 s |
| GS heartbeat timeout | 15 s |
| Default REPLAY count | 120 |

---

## Wiring and pinout

| Pin | Signal | Mode |
| --- | --- | --- |
| PA2/PA3 | USART2 TX/RX | AF7, ST-Link VCOM |
| PA5/PA6/PA7 | SPI1 SCK/MISO/MOSI | SD card |
| PB6 | SD_CS | GPIO out, idle HIGH |
| PB5 | DHT_DATA | Open drain, idle HIGH |
| PA0/PA1/PA4 | Pot/Photodiode/LM35 | ADC1 IN5/IN6/IN9 |
| PB4 | Buzzer | TIM3_CH1 PWM |
| PC9 | Heartbeat LED | GPIO out |
| PB8 | Fault LED | GPIO out |
| PA10/PB3 | SW1/SW2 | GPIO in / EXTI3 |

Clock: HSE 8 MHz, PLL to 80 MHz SYSCLK. UART link: ST-Link VCOM, 115200 8N1.

## Build and flash

STM32CubeIDE project, the IDE bundles the toolchain and ST-Link tools.
Pin config is in `kern-lite.ioc`.

1. Import the repo root as an existing project.
2. Project > Build All.
3. Run, flashes over the onboard ST-Link.

To flash an already built image without the IDE (needs STM32CubeProgrammer):

```sh
STM32_Programmer_CLI -c port=SWD -w Debug/kern-lite.elf -v -rst
```

## Ground station

Requires Python 3. All commands run from the repo root.

1. First time setup:

   ```sh
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

   > On Windows replace `.venv/bin/` with `.venv\Scripts\`. The GUI uses Tkinter; on Linux install `python3-tk` if missing.

2. Run the operator dashboard:

   ```sh
   .venv/bin/python -m dashboard
   ```

3. Connect with your port. Each connect creates a new `sessions/<timestamp>/` directory.

Other entry points:

- Headless gate probe (full end to end checklist):

  ```sh
  .venv/bin/python -m groundstation.probe --port /dev/ttyACM0
  ```

- Device simulator, to try the dashboard without hardware:

  ```sh
  .venv/bin/python -m dashboard.sim
  ```

- Python REPL for talking to the board by hand: [ground_station_cli.md](docs/ground_station_cli.md).

## Command set

| Command | Payload | Valid state | Effect |
| --- | --- | --- | --- |
| START | none | Idle | begin recording |
| STOP | none | Recording | stop recording |
| STATUS | none | any | board state snapshot |
| REPLAY | count (u16) | Idle, SD mounted | stream stored records |
| ERASE | magic `0xDEADC0DE` | Idle | wipe the log |

## Configured constants

Defined in `firmware/system/config.hpp`:

| Constant | Value | Meaning |
| --- | --- | --- |
| sample rate | 10 Hz | 100 ms sensor task period |
| `LOG_FILE_COUNT` | 4 | files in the circular log |
| `RECORDS_PER_FILE` | 256 | records per file, 1024 total |
| `META_FLUSH_EVERY_N` | 16 | metadata flush interval |
| `kUartBaud` | 115200 | link baud rate |
| `kDspWindow` | 16 | moving average window |
| `kEraseMagic` | 0xDEADC0DE | ERASE authorization magic |
| `kMaxWriteFails` | 3 | SD failures before Fault |

## Tests

- All tests (Python + host C++):

  ```sh
  make -C tests run
  ```

- Only Python suites:

  ```sh
  .venv/bin/pytest -v
  ```

- Only host C++ suites:

  ```sh
  make -C tests run-host
  ```

> CRC known answer: `CRC32("123456789") = 0xCBF43926`.

## Layout

```
firmware/            C++17 application
  system/            boot, tasks, orchestrator, config
  sensors/           LM35, DHT11, photodiode, pot, buttons
  dsp/               filters and threshold alerts
  protocol/          frame codec, CRC-32
  storage/           circular log over FatFs
  recorder/          state machine, command handling
  hal/               gpio, adc, watchdog wrappers
Core/ Drivers/
Middlewares/ FATFS/  CubeMX generated code
kern-lite.ioc        pin and peripheral config
groundstation/       Python link, telemetry, analytics
dashboard/           operator console and simulator
tests/
  host/              C++ suites (FatFs shim)
  gs/                pytest suites
  hw/                on target gate scripts
docs/                spec, design note, validation results
sessions/            dashboard run output (generated)
```
## Documentation

| Doc | Role |
|---|---|
| [`docs/project_architecture_overview.md`](docs/project_architecture_overview.md) | Implementation deep-dive: file-level mapping, concurrency map, data-flow traces. |
| [`docs/design_note.md`](docs/design_note.md) | `LogMeta` byte layout, recovery algorithm, T5 power-loss robustness evidence. |
## Team

Three people, each owning a vertical slice: a piece of the firmware, its
ground station counterpart, and the tests for both.

| Member | Firmware | Ground station |
| --- | --- | --- |
| [shalom2552](https://github.com/shalom2552) | recorder pipeline, circular storage, fault policy | dashboard, sessions, analytics |
| [Yair-Dekel](https://github.com/Yair-Dekel) | board bring-up, CRC-32/frame protocol, CubeMX/HAL glue | telemetry decode, integrity, state tracking |
| [Smallejoo](https://github.com/Smallejoo) | sensor drivers, DSP, state machine | serial link, command layer |

## License

[MIT](LICENSE)
