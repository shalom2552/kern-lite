#pragma once

#include "FreeRTOS.h"
#include "task.h"

namespace kern::tasks {

inline constexpr uint32_t kSensorStack = 512;   ///< Sensor task stack size in words
inline constexpr uint32_t kStorageStack = 768;  ///< Storage task stack size in words
inline constexpr uint32_t kCommsStack = 384;    ///< Comms task stack size in words
inline constexpr uint32_t kSystemStack = 384;   ///< System task stack size in words

inline constexpr UBaseType_t kSensorPrio = tskIDLE_PRIORITY + 2;   ///< Sensor task scheduling priority
inline constexpr UBaseType_t kStoragePrio = tskIDLE_PRIORITY + 2;  ///< Storage task scheduling priority
inline constexpr UBaseType_t kCommsPrio = tskIDLE_PRIORITY + 3;    ///< Comms task scheduling priority (timing critical)
inline constexpr UBaseType_t kSystemPrio = tskIDLE_PRIORITY + 1;   ///< System task scheduling priority (low priority background checks)

}  // namespace kern::tasks

