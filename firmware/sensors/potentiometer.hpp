/*
Potentiometer sensor driver.

file: firmware/sensors/potentiometer.hpp
author: Smallejoo
date: 2026-06-07
*/

#pragma once

#include "stm32l4xx_hal.h"
#include "../hal/adc.hpp"
#include "../system/board.hpp"

namespace kern::sensors {

/**
 * @brief Driver class for the rotary potentiometer analog input.
 */
class Potentiometer {
public:
	/**
	 * @brief Construct a Potentiometer instance linked to an ADC controller.
	 * @param adc Pointer to the ADC handle structure.
	 */
	explicit Potentiometer(ADC_HandleTypeDef* adc)
	: m_adc(adc)
	{
	}

	/**
	 * @brief Initialize the Potentiometer sensor driver.
	 */
	void init()
	{
		//ADC init is done by CubeMX/HAL
	}

	/**
	 * @brief Read potentiometer value normalized between 0.0f and 1.0f.
	 * @return Normalized potentiometer position.
	 */
	float readNormalized()
	{
		if (m_adc == nullptr) {
			return 0.0f;
		}

		//use shared ADC wrapper, not call HAL directly
		uint32_t raw = kern::hal::adc::read(*m_adc, kern::board::AdcChannel::Pot);

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
