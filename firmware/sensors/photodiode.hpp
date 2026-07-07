#pragma once

#include "stm32l4xx_hal.h"
#include "../hal/adc.hpp"
#include "../system/board.hpp"

namespace kern::sensors {

class Photodiode {
public:
	explicit Photodiode(ADC_HandleTypeDef* adc)
	: m_adc(adc)
	{
	}

	void init()
	{
		//ADC init is done by CubeMX/HAL
	}

	float readNormalized()
	{
		if (m_adc == nullptr) {
			return 0.0f;
		}

		//use shared ADC wrapper, not call HAL directly
		uint32_t raw = kern::hal::adc::read(*m_adc, kern::board::AdcChannel::Photodiode);

		float volts = kern::hal::adc::toVolts(raw);
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
	ADC_HandleTypeDef* m_adc = nullptr;
};

} // namespace kern::sensors
