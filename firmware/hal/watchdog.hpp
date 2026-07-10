#pragma once

#include "stm32l4xx_hal.h"

namespace kern::hal::watchdog {

/**
 * @brief Kick (refresh) the independent watchdog timer to prevent system reset.
 * @param h Handle to the IWDG instance.
 */
inline void kick(IWDG_HandleTypeDef& h) { HAL_IWDG_Refresh(&h); }

}
