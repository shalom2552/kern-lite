/*
Button polling helper for SW1 short and long press detection.

file: firmware/sensors/buttons.hpp
author: Smallejoo
date: 2026-06-07
*/
#pragma once

#include "stm32l4xx_hal.h"
#include "../system/board.hpp"

namespace kern::sensors {

/**
 * @brief Types of button presses detected.
 */
enum class PressType {
	None,  ///< No press event detected
	Short, ///< Short press event (held for >= 30ms and < 1000ms)
	Long   ///< Long press event (held for >= 1000ms)
};

/**
 * @brief Button polling and press detection helper for SW1.
 */
class Buttons {
public:
	/**
	 * @brief Initialize/reset the button polling state variables.
	 */
	void init()
	{
		m_wasPressed = false;
		m_pressStartMs = 0;
		m_longReported = false;
	}

	/**
	 * @brief Poll the SW1 button state and check for short/long press transitions.
	 * @return Detected PressType (None, Short, or Long).
	 */
	PressType pollSw1()
	{
		bool pressed = isPressed();

		if (pressed && !m_wasPressed) {
			m_pressStartMs = HAL_GetTick();
			m_longReported = false;
			m_wasPressed = true;
			return PressType::None;
		}

		if (pressed && m_wasPressed) {
			uint32_t heldMs = HAL_GetTick() - m_pressStartMs;

			if (!m_longReported && heldMs >= 1000u) {
				m_longReported = true;
				return PressType::Long;
			}

			return PressType::None;
		}

		if (!pressed && m_wasPressed) {
			uint32_t heldMs = HAL_GetTick() - m_pressStartMs;
			m_wasPressed = false;

			if (heldMs >= 30u && heldMs < 1000u) {
				return PressType::Short;
			}
		}

		return PressType::None;
	}

private:
	/**
	 * @brief Check if SW1 button is currently physically pressed down.
	 * @return true if pressed, false otherwise.
	 */
	bool isPressed() const
	{

		uint16_t pinMask = static_cast<uint16_t>(1u << kern::board::SW1.n);

		//active LOW button
		return HAL_GPIO_ReadPin(kern::board::SW1.port, pinMask) == GPIO_PIN_RESET;
	}

private:
	bool m_wasPressed = false;
	uint32_t m_pressStartMs = 0;
	bool m_longReported = false;
};

} // namespace kern::sensors
