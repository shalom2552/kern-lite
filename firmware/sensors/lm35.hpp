#pragma once

#include "stm32l4xx_hal.h"
#include "../hal/adc.hpp"
#include "../system/board.hpp"

namespace kern::sensors {

class Lm35
{
public:
	explicit Lm35(ADC_HandleTypeDef* adc)
	: m_adc(adc)
	{
	}

	void init()
	{
		// ADC init is done by CubeMX/HAL
	}

	float readCelsius()
	{
		if (m_adc == nullptr) {
			return 0.0f;
		}

		// use shared ADC wrapper, not call HAL directly
		uint32_t raw = kern::hal::adc::read(*m_adc, kern::board::AdcChannel::Lm35);

		float volts = kern::hal::adc::toVolts(raw);

		// LM35 conversion from spec: volts * 100 = degC
		return volts * 100.0f;
	}

private:
	ADC_HandleTypeDef* m_adc = nullptr;
};

} // namespace kern::sensors
