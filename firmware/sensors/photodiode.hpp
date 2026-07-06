#pragma once

#include "stm32l4xx_hal.h"

namespace kern::sensors {

class Photodiode {
public:
	explicit Photodiode(ADC_HandleTypeDef* adc)
	: m_adc(adc)
	{}

	void init()
	{
	}

	float readNormalized()
	{
		uint32_t raw = readRaw();
		float volts = toVolts(raw);
		float normalized = volts / 3.3f;

		if (normalized < 0.0f) {
			normalized = 0.0f;
		}

		if (normalized > 1.0f) {
			normalized = 1.0f;
		}

		return normalized;
	}

private:
	uint32_t readRaw()
	{
		if (m_adc == nullptr) {
			return 0;
		}

		ADC_ChannelConfTypeDef sConfig{};
		sConfig.Channel = ADC_CHANNEL_6;
		sConfig.Rank = ADC_REGULAR_RANK_1;
		sConfig.SamplingTime = ADC_SAMPLETIME_47CYCLES_5;
		sConfig.SingleDiff = ADC_SINGLE_ENDED;
		sConfig.OffsetNumber = ADC_OFFSET_NONE;
		sConfig.Offset = 0;

		if (HAL_ADC_ConfigChannel(m_adc, &sConfig) != HAL_OK) {
			return 0;
		}

		HAL_ADC_Start(m_adc);

		if (HAL_ADC_PollForConversion(m_adc, 10) != HAL_OK) {
			HAL_ADC_Stop(m_adc);
			return 0;
		}

		uint32_t raw = HAL_ADC_GetValue(m_adc);
		HAL_ADC_Stop(m_adc);

		return raw;
	}

	float toVolts(uint32_t raw)
	{
		return (static_cast<float>(raw) * 3.3f) / 4095.0f;
	}

private:
	ADC_HandleTypeDef* m_adc = nullptr;
};

} // namespace kern::sensors
