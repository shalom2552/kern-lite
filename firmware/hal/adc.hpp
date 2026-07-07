/*
ADC wrapper config for the gate.

file: firmware/hal/adc.hpp
author: Smallejoo
date: 2026-06-07
*/

#pragma once
#include "stm32l4xx_hal.h"
#include "../system/board.hpp"
#include <cstdint>

namespace kern::hal::adc {

inline uint32_t read(ADC_HandleTypeDef& adc, kern::board::AdcChannel channel)
{
	ADC_ChannelConfTypeDef sConfig{};

	sConfig.Channel = static_cast<uint32_t>(channel);
	sConfig.Rank = ADC_REGULAR_RANK_1;
	sConfig.SamplingTime = ADC_SAMPLETIME_47CYCLES_5;
	sConfig.SingleDiff = ADC_SINGLE_ENDED;
	sConfig.OffsetNumber = ADC_OFFSET_NONE;
	sConfig.Offset = 0;

	// all ADC channel config goes through this wrapper
	if (HAL_ADC_ConfigChannel(&adc, &sConfig) != HAL_OK) {
		return 0;
	}

	if (HAL_ADC_Start(&adc) != HAL_OK) {
		return 0;
	}

	if (HAL_ADC_PollForConversion(&adc, 10) != HAL_OK) {
		HAL_ADC_Stop(&adc);
		return 0;
	}

	uint32_t raw = HAL_ADC_GetValue(&adc);

	HAL_ADC_Stop(&adc);

	return raw;
}

inline float toVolts(uint32_t raw)
{
	//assumes 12-bit ADC and 3.3V reference
	return (static_cast<float>(raw) * 3.3f) / 4095.0f;
}

} // namespace kern::hal::adc
