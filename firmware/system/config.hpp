/*
configuration constants.

file: firmware/system/config.hpp
author: Smallejoo
date: 2026-06-07
*/
#pragma once

#include <cstdint>
#include <cstddef>

#include "../dsp/threshold_detector.hpp"

namespace kern::config {

inline constexpr uint32_t kUartBaud = 115200;     ///< UART baud rate for serial communication
inline constexpr uint32_t kSensorPeriodMs = 100;   ///< Period of sensor polling task in milliseconds
inline constexpr uint32_t kStoragePeriodMs = 100;  ///< Period of storage recording task in milliseconds
inline constexpr uint32_t kCommsPeriodMs = 10;     ///< Period of protocol communications task in milliseconds
inline constexpr uint32_t kSystemPeriodMs = 50;    ///< Period of system check task in milliseconds
inline constexpr uint32_t kMetaFlushEveryN = 16;   ///< Flush metadata to SD card every N record writes
inline constexpr uint8_t kLogFileCount = 4;        ///< Number of log files in circular buffer
inline constexpr uint16_t kRecordsPerFile = 256;   ///< Maximum number of records stored per log file
inline constexpr uint32_t kEraseMagic = 0xDEADC0DEu; ///< Authorization code for erasing logs


inline constexpr std::size_t kDspWindow = 16;      ///< Moving average window size for DSP pipelines

/**
 * @brief Threshold configuration for LM35 temperature sensor.
 */
inline constexpr kern::dsp::ThresholdConfig kLm35Threshold {
    10.0f,//low
	40.0f,//high
	2.0f  //hysteresis
};

/**
 * @brief Threshold configuration for Photodiode light sensor.
 */
inline constexpr kern::dsp::ThresholdConfig kPhotoThreshold {
    0.05f,
	0.95f,
	0.05f
};

/**
 * @brief Threshold configuration for Potentiometer sensor.
 */
inline constexpr kern::dsp::ThresholdConfig kPotThreshold {
    0.02f,
	0.98f,
	0.02f
};

/**
 * @brief Threshold configuration for DHT11 temperature.
 */
inline constexpr kern::dsp::ThresholdConfig kDhtTempThreshold {
    5.0f,
	45.0f,
	2.0f
};

/**
 * @brief Threshold configuration for DHT11 humidity.
 */
inline constexpr kern::dsp::ThresholdConfig kDhtHumThreshold {
    10.0f,
	90.0f,
	5.0f
};

} // namespace kern::config
