#include "radiation_latch.hpp"

namespace kern::sensors {

void RadiationLatch::init()
{

	m_sem = xSemaphoreCreateBinaryStatic(&m_semStorage);

	taskENTER_CRITICAL();
	m_count = 0;
	taskEXIT_CRITICAL();
}

void RadiationLatch::isr()
{
	++m_count;

	if (m_sem != nullptr) {
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
