#pragma once

#include "stm32l4xx_hal.h"
#include "../system/board.hpp"

namespace kern::sensors {

enum class PressType {
	None,
	Short,
	Long
};

class Buttons {
public:
	void init()
	{
		m_wasPressed = false;
		m_pressStartMs = 0;
		m_longReported = false;
	}

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
