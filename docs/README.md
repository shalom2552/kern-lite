# KERN-LITE

Embedded black-box data logger.

MCU - STM32L476RG.

## Status

- [x] Phase 0 — Project setup, RTOS smoke test
- [x] Phase 1 — CRC-32 + frame codec
- [x] Phase 2 — UART round-trip (STATUS/ACK)
- [x] Phase 3 — Sensors, DSP, live SensorRecord stream
- [x] Phase 4 — Circular file storage, replay, recovery
- [x] Phase 5 — State machine, full command set
- [x] Phase 6 — Ground station analytics
- [ ] Phase 7 — Fault injection, validation, demo

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

## Configured constants

| Constant | Value |
|---|---|
| `LOG_FILE_COUNT` | 4 |
| `RECORDS_PER_FILE` | 256 |
| `META_FLUSH_EVERY_N` | 16 |
| Sample rate | 10 Hz |
| UART | 115200 baud, USART2 |
| `ERASE_MAGIC` | `0xDEADC0DE` |

---

## Pinout

| Pin | Signal | Mode |
|---|---|---|
| PA2/PA3 | USART2 TX/RX | AF7, ST-Link VCOM |
| PA5/PA6/PA7 | SPI1 SCK/MISO/MOSI | SD card |
| PB6 | SD_CS | GPIO out, idle HIGH |
| PB5 | DHT_DATA | Open-drain, idle HIGH |
| PA0/PA1/PA4 | Pot/Photodiode/LM35 | ADC1 IN5/IN6/IN9 |
| PB4 | Buzzer | TIM3_CH1 PWM |
| PC9 | Heartbeat LED | GPIO out |
| PB8 | Fault LED | GPIO out |
| PA10/PB3 | SW1/SW2 | GPIO in / EXTI3 |

Clock: HSE 8MHz → PLL (M=1,N=20,R=2) → **80MHz SYSCLK**.

## Structure

```
firmware/    hal · sensors · dsp · protocol · storage · recorder · system
groundstation/  Python GS (planned)
tests/       host/ (C++) · gs/ (pytest)
docs/        full spec + design notes
```

## Team

[shalom2552](https://github.com/shalom2552), [Yair-Dekel](https://github.com/Yair-Dekel), [Smallejoo](https://github.com/Smallejoo)
