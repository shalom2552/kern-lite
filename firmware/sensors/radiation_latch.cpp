#include "radiation_latch.hpp"
#include "main.h"

namespace kern::sensors {

RadiationLatch* g_radiationLatch = nullptr;

void RadiationLatch::init()
{

	// Create the semaphore used to wake tasks and make this instance globally
	// visible to the GPIO interrupt callback.
	m_sem = xSemaphoreCreateBinaryStatic(&m_semStorage);
	g_radiationLatch = this;

	taskENTER_CRITICAL();
	m_count = 0;
	taskEXIT_CRITICAL();
}

void RadiationLatch::isr()
{
	// Count first so no pulse is lost even if the task wakes later.
	++m_count;

	if (m_sem != nullptr) {
		// Wake the task side from interrupt context without blocking the ISR.
		BaseType_t higherPriorityTaskWoken = pdFALSE;
		xSemaphoreGiveFromISR(m_sem, &higherPriorityTaskWoken);
		portYIELD_FROM_ISR(higherPriorityTaskWoken);
	}
}

bool RadiationLatch::consumeEvent()
{
	if (m_sem == nullptr) {
		return false;
	}

	// Consume one notification token before decrementing the protected count.
	if (xSemaphoreTake(m_sem, 0) != pdTRUE) {
		return false;
	}

	taskENTER_CRITICAL();

	if (m_count > 0) {
		--m_count;
		taskEXIT_CRITICAL();
		return true;
	}

	taskEXIT_CRITICAL();
	return false;
}

} // namespace kern::sensors

extern "C" void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
	// Only route the configured external interrupt pin to this latch; other
	// GPIO interrupts may belong to unrelated board features.
	if (GPIO_Pin == SW2_Pin && kern::sensors::g_radiationLatch != nullptr) {
		kern::sensors::g_radiationLatch->isr();
	}
}
