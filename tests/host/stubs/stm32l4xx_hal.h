#pragma once

#include <cstdint>

struct UART_HandleTypeDef {};
struct ADC_HandleTypeDef {};
struct IWDG_HandleTypeDef {};
struct GPIO_TypeDef {};

enum GPIO_PinState {
    GPIO_PIN_RESET = 0,
    GPIO_PIN_SET = 1
};

inline GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef*, uint16_t) { return GPIO_PIN_SET; }
inline void HAL_GPIO_WritePin(GPIO_TypeDef*, uint16_t, GPIO_PinState) {}
inline void HAL_GPIO_TogglePin(GPIO_TypeDef*, uint16_t) {}
inline uint32_t HAL_GetTick() { return 0; }
inline void HAL_UART_Receive_IT(UART_HandleTypeDef*, uint8_t*, uint16_t) {}
inline void HAL_UART_Transmit(UART_HandleTypeDef*, uint8_t*, uint16_t, uint32_t) {}
inline void HAL_IWDG_Refresh(IWDG_HandleTypeDef*) {}
inline void NVIC_SystemReset() {}

inline GPIO_TypeDef g_gpioa{};
inline GPIO_TypeDef g_gpiob{};
inline GPIO_TypeDef g_gpioc{};

#define GPIOA (&g_gpioa)
#define GPIOB (&g_gpiob)
#define GPIOC (&g_gpioc)

#define ADC_CHANNEL_5 5u
#define ADC_CHANNEL_6 6u
#define ADC_CHANNEL_9 9u
