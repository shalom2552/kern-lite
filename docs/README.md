# KERN-LITE

Embedded black-box data logger.

MCU - STM32L476RG.

## Status

- [x] Phase 0 — Project setup, RTOS smoke test
- [ ] Phase 1 — CRC-32 + frame codec
- [ ] Phase 2 — UART round-trip (STATUS/ACK)
- [ ] Phase 3 — Sensors, DSP, live SensorRecord stream
- [ ] Phase 4 — Circular file storage, replay, recovery
- [ ] Phase 5 — State machine, full command set
- [ ] Phase 6 — Ground station analytics
- [ ] Phase 7 — Fault injection, validation, demo

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

Shalom, Yair-Dekel, Smallejoo