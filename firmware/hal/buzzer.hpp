#pragma once

#include "stm32l4xx_hal.h"

#include <cstdint>

namespace kern::hal::buzzer {

inline constexpr uint32_t kTimerClockHz = 1000000u; // TIM3 counter clock after the /80 prescaler

/**
 * @brief Start a continuous tone at the given frequency on TIM3_CH1 (PB4).
 * @param h Handle to the PWM timer instance.
 * @param freqHz Tone frequency in hertz; must be non-zero.
 */
inline void toneOn(TIM_HandleTypeDef& h, uint32_t freqHz)
{
    if (freqHz == 0u) {
        HAL_TIM_PWM_Stop(&h, TIM_CHANNEL_1);
        return;
    }

    uint32_t period = kTimerClockHz / freqHz;
    __HAL_TIM_SET_AUTORELOAD(&h, period - 1u);
    __HAL_TIM_SET_COMPARE(&h, TIM_CHANNEL_1, period / 2u);
    __HAL_TIM_SET_COUNTER(&h, 0u);
    HAL_TIM_PWM_Start(&h, TIM_CHANNEL_1);
}

/**
 * @brief Silence the buzzer.
 * @param h Handle to the PWM timer instance.
 */
inline void toneOff(TIM_HandleTypeDef& h)
{
    HAL_TIM_PWM_Stop(&h, TIM_CHANNEL_1);
}

} // namespace kern::hal::buzzer
