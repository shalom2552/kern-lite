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

## Running the Ground Station (Python)
Python tests runs in an isolated Python virtualenv (`.venv`) for portability and separation from system packages. <br>
Activate/invoke it per-OS:

<details>
<summary>Linux / macOS / WSL</summary>
<br>
  
First-time setup:
```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Run tests:
```bash
.venv/bin/pytest -v
```
Run a Python file:
```bash
.venv/bin/python <path/to/file.py>
```
Check Python syntax:
```bash
.venv/bin/python3 -m py_compile <path-to-file> && echo OK || echo FAIL
```
</details>

<details>
<summary>Windows (cmd)</summary>
<br>
  
First-time setup:
```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```
Run tests:
```bash
.venv\Scripts\pytest -v
```
Run a Python file:
```bash
.venv\Scripts\python <path\to\file.py>
```
Check Python syntax:
```bash
.venv\Scripts\python -m py_compile <path-to-file> && echo OK || echo FAIL
```
</details>

Run all commands from repo root.

### Dashboard

Full operator console (connect, commands, live values, charts, storage ring,
link quality, events, timeline, session recording/reload, exports):
```bash
.venv/bin/python -m dashboard
```
Pick the board's serial port and press Connect. Every connect creates a new
`sessions/<timestamp>/` directory; closing the window or Ctrl+C shuts down
cleanly and flushes the session files.

To try the dashboard without hardware, run the device simulator and connect
to the pty path it prints:
```bash
.venv/bin/python -m dashboard.sim
```

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
