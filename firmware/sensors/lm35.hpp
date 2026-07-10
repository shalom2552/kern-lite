/*
LM35 temperature sensor driver.

file: firmware/sensors/lm35.hpp
author: Smallejoo
date: 2026-06-07
*/
#pragma once

#include "stm32l4xx_hal.h"
#include "../hal/adc.hpp"
#include "../system/board.hpp"

namespace kern::sensors {

/**
 * @brief Driver class for the LM35 analog temperature sensor.
 */
class Lm35
{
public:
	/**
	 * @brief Construct an Lm35 sensor instance linked to an ADC controller.
	 * @param adc Pointer to the ADC handle structure.
	 */
	explicit Lm35(ADC_HandleTypeDef* adc)
	: m_adc(adc)
	{
	}

	/**
	 * @brief Initialize the LM35 sensor driver.
	 */
	void init()
	{
		// ADC init is done by CubeMX/HAL
	}

	/**
	 * @brief Read temperature in degrees Celsius.
	 * @return Measured temperature in degrees Celsius, or 0.0f on error.
	 */
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
