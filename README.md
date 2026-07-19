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

## Milestones

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

## Getting started

### Build and flash

STM32CubeIDE project, the IDE bundles the toolchain and ST-Link tools.

1. Import the repo root as an existing project.
2. Project > Build All.
3. Run, flashes over the onboard ST-Link.

Sensor hookup is under [Wiring and pinout](#wiring-and-pinout).

### Ground station setup

Requires Python 3. All commands run from the repo root.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> On Windows replace `.venv/bin/` with `.venv\Scripts\`.\
> On Linux install `python3-tk` if missing.

## Usage

### Dashboard

Run the operator dashboard:

```sh
.venv/bin/python -m dashboard
```

Then connect with your port. Each connect creates a new `sessions/<timestamp>/` directory.

### Command set

| Command | Payload | Valid state | Effect |
| --- | --- | --- | --- |
| START | none | Idle | begin recording |
| STOP | none | Recording | stop recording |
| STATUS | none | any | board state snapshot |
| REPLAY | count (u16) | Idle, SD mounted | stream stored records |
| ERASE | magic `0xDEADC0DE` | Idle | wipe the log |

States: Idle, Recording, Fault. START begins recording, STOP or a short press
on SW1 returns to Idle. Three SD write failures in a row enter Fault, a
successful remount recovers.

### Other entry points

- Headless gate probe (full end to end checklist):

  ```sh
  .venv/bin/python -m groundstation.probe --port /dev/ttyACM0
  ```

- Device simulator, to try the dashboard without hardware:

  ```sh
  .venv/bin/python -m dashboard.sim
  ```

- Python REPL for talking to the board by hand: [ground_station_cli.md](docs/ground_station_cli.md).

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

## Reference

In this section:

- [Wiring and pinout](#wiring-and-pinout), where each sensor connects
- [Protocol](#protocol), what travels over the UART
- [Record format](#record-format), the 32 byte stored sample
- [Firmware tasks](#firmware-tasks), what runs and when
- [Constants](#constants), the tunable numbers

### Wiring and pinout

Every external connection on the Nucleo, by pin:

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

### Protocol

Everything on the wire travels in frames.

#### Frame layout

Every frame has the same shape, byte by byte:

| Offset | Field | Size (bytes) | Value |
| :---: | --- | :---: | --- |
| 0 | STX | 1 | 0xAB |
| 1 | type | 1 | opcode |
| 2 | length | 2 | payload length, u16 LE |
| 4 | payload | 0 to 256 | command or telemetry data |
| 4+len | CRC-32 | 4 | over type, length and payload, LE |
| 8+len | ETX | 1 | 0xCD |

Overhead 9 bytes, so 265 max per frame.

#### Frame types

All frames, by opcode:

| Opcode | Frame | Payload |
| :---: | --- | --- |
| 0x01 | START | none |
| 0x02 | STOP | none |
| 0x03 | STATUS | none |
| 0x04 | REPLAY | count (u16 LE) |
| 0x06 | ERASE | magic (u32 LE) |
| 0x10 | RECORD | 32 byte SensorRecord |
| 0x12 | STATUS reply | 14 byte status block |
| 0x20 | ACK | none |
| 0x21 | NACK | reason (u8) |

NACK reasons: CrcError 1, BadCommand 2, InvalidState 3, StorageError 4, BadMagic 6.

#### STATUS reply

The reply to STATUS, 14 bytes:

| Offset | Field | Type | Meaning |
| :---: | --- | :---: | --- |
| 0 | state | u8 | FSM state (0/1/2) |
| 1 | sd_mounted | u8 | 1 if the card is mounted |
| 2 | file_count | u8 | files in the circular log |
| 3 | current_file | u8 | file being written |
| 4 | total_records | u32 | total records written |
| 8 | wrap_count | u32 | times the ring wrapped |
| 12 | write_index | u16 | write position in file |

### Record format

`SensorRecord` is 32 bytes, packed, one per sample. Byte by byte:

| Offset | Field | Type | Meaning |
| :---: | --- | :---: | --- |
| 0 | timestamp | u32 | seconds |
| 4 | ms | u16 | millisecond part |
| 6 | seq | u16 | wraps at 65536 |
| 8 | lm35_c | i16 | LM35 temp, x10 degrees C |
| 10 | dht_temp_c | i16 | DHT11 temp, x10 degrees C |
| 12 | dht_hum | u16 | DHT11 humidity, x10 percent |
| 14 | light | u16 | photodiode, normalized to 65535 |
| 16 | pot | u16 | potentiometer, normalized to 65535 |
| 18 | alert_bits | u8 | DSP threshold alerts |
| 19 | state | u8 | FSM state (0/1/2) |
| 20 | fault_bits | u8 | sensor faults |
| 21 | reserved | u8[7] | |
| 28 | crc32 | u32 | over bytes 0 to 27 |

### Firmware tasks

Four FreeRTOS tasks share the MCU:

| Task | Period | Priority | Stack | Role |
| --- | :---: | :---: | :---: | --- |
| Sensor | 100 ms | idle+2 | 512 | sample, filter, publish the record, stream it live while recording |
| Storage | 100 ms | idle+2 | 768 | mount the card, write one record per sample, remount after faults |
| Comms | 10 ms | idle+3 | 384 | poll the UART link and dispatch commands |
| System | 50 ms | idle+1 | 384 | watchdog, LEDs, buzzer, buttons, 5 s STATUS heartbeat |

### Constants

Defined in `firmware/system/config.hpp`:

| Constant | Value | Meaning |
| --- | :---: | --- |
| sample rate | 10 Hz | 100 ms sensor task period |
| `LOG_FILE_COUNT` | 4 | files in the circular log |
| `RECORDS_PER_FILE` | 256 | records per file, 1024 total |
| `META_FLUSH_EVERY_N` | 16 | metadata flush interval |
| `kUartBaud` | 115200 | link baud rate |
| `kDspWindow` | 16 | moving average window |
| `kEraseMagic` | 0xDEADC0DE | ERASE authorization magic |
| `kMaxWriteFails` | 3 | SD failures before Fault |

## Repo layout

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

| Doc | What |
| --- | --- |
| [design_note.md](docs/design_note.md) | storage metadata and recovery |
| [project_architecture_overview.md](docs/project_architecture_overview.md) | file level walkthrough |
| [ground_station_cli.md](docs/ground_station_cli.md) | REPL for talking to the board |
| [groundstation_api.md](docs/groundstation_api.md) | Python API reference |

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
