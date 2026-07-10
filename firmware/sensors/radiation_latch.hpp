#pragma once

#include "FreeRTOS.h"
#include "semphr.h"

#include <cstdint>

namespace kern::sensors {

/**
 * @brief Class for tracking radiation interrupt events captured by pin interrupts.
 */
class RadiationLatch {
public:
	/**
	 * @brief Initialize the binary semaphore and reset event count.
	 */
	void init();

	//call this from EXTI ISR/callback
	/**
	 * @brief ISR handler to register a radiation event and unblock waiting tasks.
	 */
	void isr();

	//Sensor task calls this to consume one event
	/**
	 * @brief Try to consume a registered radiation latch event.
	 * @return true if an event was available and successfully consumed, false otherwise.
	 */
	bool consumeEvent();

private:
	StaticSemaphore_t m_semStorage{};
	SemaphoreHandle_t m_sem = nullptr;

	volatile uint32_t m_count = 0;
};

extern RadiationLatch* g_radiationLatch;

} // namespace kern::sensors
