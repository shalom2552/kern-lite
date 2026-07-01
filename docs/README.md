# KERN-LITE

Embedded black-box data logger — STM32L476RG + CMSIS-RTOS2/FreeRTOS + FatFs, paired with a Python ground station over a CRC-32-protected binary protocol.

Samples 5 sensor channels at 10Hz, filters/validates them, writes fixed 32-byte records into a fault-recoverable circular SD-card ring, and streams live telemetry to a GS that visualizes, verifies, and archives it.

## Status

- [x] Phase 0 — Project setup, RTOS smoke test
- [ ] Phase 1 — CRC-32 + frame codec
- [ ] Phase 2 — UART round-trip (STATUS/ACK)
- [ ] Phase 3 — Sensors, DSP, live SensorRecord stream
- [ ] Phase 4 — Circular file storage, replay, recovery
- [ ] Phase 5 — State machine, full command set
- [ ] Phase 6 — Ground station analytics
- [ ] Phase 7 — Fault injection, validation, demo

## Architecture

```
+------------------------- STM32L4 / CMSIS-RTOS2 -------------------------+
| Sensors -> Sensor Task -> SensorBus -> Storage Task -> FatFs / SD       |
|                              |    ^                                     |
|                              +-> live RECORD -> CommLink / Comms Task   |
| System Task: watchdog, LEDs, buttons, framed STATUS heartbeat           |
+-------------------------- UART2 115200 8N1 -----------------------------+
                               |
                               v
+------------------------------ Python GS -------------------------------+
| SerialLink -> Frame Decoder -> Integrity -> Models -> UI / Session      |
+---------------------------------------------------------------------------+
```

4 static RTOS tasks: **Sensor** (100ms), **Storage** (100ms), **Comms** (10ms poll), **System** (50ms — watchdog, LEDs, heartbeat).

## Build & flash

1. Open `kern-lite.ioc` in STM32CubeIDE → Build All
2. Flash via ST-Link
3. Serial terminal, 115200 8N1 → expect `KERN-LITE ALIVE` @ 1Hz + PC9 blink

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

**Layering rule:** protocol/dsp/recorder logic must not depend on STM32 headers — host-testable.

## Protocol

`[STX 0xAB][TYPE][LEN][PAYLOAD 0..256][CRC32][ETX 0xCD]` over USART2, little-endian.
CRC-32/IEEE 802.3, KAT: `CRC32("123456789") == 0xCBF43926`.
Commands: `START`, `STOP`, `STATUS`, `REPLAY N`, `ERASE <magic>` → `RECORD`/`STATUS`/`ACK`/`NACK`.

## Key constants

| | |
|---|---|
| Sample rate | 10 Hz |
| Ring | 4 files × 256 records (~102s @10Hz) |
| Metadata flush | every 16 records |
| Erase magic | `0xDEADC0DE` |
| STATUS heartbeat | 5s / GS timeout 15s |

## Testing

```bash
cd tests/host && make && ./test_codec && ./test_dsp && ./test_storage && ./test_fsm
cd tests/gs && pytest -v
```

## Team

Shalom, Yair-Dekel, Smallejoo