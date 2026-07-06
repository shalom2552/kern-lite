#pragma once

#include "stm32l4xx_hal.h"
#include "../system/board.hpp"

#include <cstdint>

namespace kern::sensors {

class Dht11 {
public:
	enum class Status {
		Ok,
		Timeout,
		CrcError
	};

	void init();

	Status read(float& tempC, float& humidity);

private:
	void pinOutput();
	void pinInput();

	void writePin(GPIO_PinState state);
	GPIO_PinState readPin() const;

	bool waitForLevel(GPIO_PinState level, uint32_t startMs);
	bool timedOut(uint32_t startMs) const;

	void delayUs(uint32_t us);

private:
	static constexpr uint32_t kMaxReadMs = 5u;
};

} // namespace kern::sensors
