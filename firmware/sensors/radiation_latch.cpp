#include "radiation_latch.hpp"
#include "main.h"

namespace kern::sensors {

RadiationLatch* g_radiationLatch = nullptr;

void RadiationLatch::init()
{

	m_sem = xSemaphoreCreateBinaryStatic(&m_semStorage);
	g_radiationLatch = this;

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

extern "C" void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
	if (GPIO_Pin == SW2_Pin && kern::sensors::g_radiationLatch != nullptr) {
		kern::sensors::g_radiationLatch->isr();
	}
}
