#pragma once

#include "FreeRTOS.h"

struct StaticSemaphore_t {
    int dummy;
};

using SemaphoreHandle_t = StaticSemaphore_t*;

inline SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t* storage)
{
    return storage;
}

inline BaseType_t xSemaphoreTake(SemaphoreHandle_t, TickType_t)
{
    return pdTRUE;
}

inline void xSemaphoreGive(SemaphoreHandle_t) {}
