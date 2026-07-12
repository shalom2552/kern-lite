#pragma once

#include <cstdint>

using TickType_t = uint32_t;
using BaseType_t = int;

#define pdTRUE 1
#define pdFALSE 0
#define portMAX_DELAY 0xFFFFFFFFu
#define pdMS_TO_TICKS(ms) (ms)
