/*
Double-buffered SensorRecord bus for sharing latest sensor data.

file: firmware/recorder/sensor_bus.hpp
author: Smallejoo
date: 2026-06-07
*/

#pragma once

#include "../storage/sensor_record.hpp"
#include "FreeRTOS.h"
#include "semphr.h"

namespace kern::recorder {

/**
 * @brief Thread-safe bus for sharing the latest SensorRecord between the Sensor task and other tasks.
 */
class SensorBus {
public:
    /**
     * @brief Initialize the static mutex used for thread-safe access to the sensor bus.
     */
    void init() { m_mutex = xSemaphoreCreateMutexStatic(&m_mutexStorage); }

    /**
     * @brief Publish a new sensor record to the bus, updating the cached value.
     * @param r The new SensorRecord.
     */
    void publish(const storage::SensorRecord& r) {
        if (m_mutex && xSemaphoreTake(m_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            m_latest = r;
            xSemaphoreGive(m_mutex);
        }
    }

    /**
     * @brief Retrieve a copy of the latest published sensor record from the bus.
     * @return The latest SensorRecord.
     */
    storage::SensorRecord latest() {
        storage::SensorRecord r{};
        if (m_mutex && xSemaphoreTake(m_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
            r = m_latest;
            xSemaphoreGive(m_mutex);
        }
        return r;
    }
private:
    StaticSemaphore_t m_mutexStorage{};
    SemaphoreHandle_t m_mutex = nullptr;
    storage::SensorRecord m_latest{};
};

}
