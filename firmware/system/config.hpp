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

inline constexpr uint32_t kUartBaud = 115200;
inline constexpr uint32_t kSensorPeriodMs = 100;
inline constexpr uint32_t kStoragePeriodMs = 100;
inline constexpr uint32_t kCommsPeriodMs = 10;
inline constexpr uint32_t kSystemPeriodMs = 50;
inline constexpr uint32_t kMetaFlushEveryN = 16;
inline constexpr uint8_t kLogFileCount = 4;
inline constexpr uint16_t kRecordsPerFile = 256;
inline constexpr uint32_t kEraseMagic = 0xDEADC0DEu;


inline constexpr std::size_t kDspWindow = 16;

inline constexpr kern::dsp::ThresholdConfig kLm35Threshold {
    10.0f,//low
	40.0f,//high
	2.0f  //hysteresis
};

inline constexpr kern::dsp::ThresholdConfig kPhotoThreshold {
    0.05f,
	0.95f,
	0.05f
};

inline constexpr kern::dsp::ThresholdConfig kPotThreshold {
    0.02f,
	0.98f,
	0.02f
};

inline constexpr kern::dsp::ThresholdConfig kDhtTempThreshold {
    5.0f,
	45.0f,
	2.0f
};

inline constexpr kern::dsp::ThresholdConfig kDhtHumThreshold {
    10.0f,
	90.0f,
	5.0f
};

} // namespace kern::config
