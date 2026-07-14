#pragma once

#include <cstdint>
#include <cstddef>

namespace kern::storage {

#pragma pack(push, 1)

/**
 * @brief Representation of a single sensor record logged to storage.
 */
struct SensorRecord {
    uint32_t timestamp; // Epoch timestamp in seconds.
    uint16_t ms;        // Millisecond component of timestamp.
    uint16_t seq;       // Sequence number incremented for each record.
    int16_t lm35_c;     // Temperature reading from LM35 (degrees C x10).
    int16_t dht_temp_c; // Temperature reading from DHT11 (degrees C x10).
    uint16_t dht_hum;   // Humidity reading from DHT11 (%RH x10).
    uint16_t light;     // Normalized light sensor reading (x65535).
    uint16_t pot;       // Normalized potentiometer reading (x65535).
    uint8_t alert_bits; // Bitmask representing active DSP alerts.
    uint8_t state;      // Current recorder state representation.
    uint8_t fault_bits; // Bitmask representing sensor faults.
    uint8_t reserved[7];// Reserved padding bytes.
    uint32_t crc32;     // CRC32 checksum over the first 28 bytes of the record.
};

#pragma pack(pop)

static_assert(sizeof(SensorRecord) == 32);
static_assert(offsetof(SensorRecord, crc32) == 28);

inline constexpr uint8_t kFaultLm35Range = 0x01;  // Fault flag: LM35 temperature out of range
inline constexpr uint8_t kFaultDhtTimeout = 0x02; // Fault flag: DHT11 communication timeout
inline constexpr uint8_t kFaultDhtBadData = 0x04; // Fault flag: DHT11 checksum failure
inline constexpr uint8_t kFaultLightStuck = 0x08; // Fault flag: Photodiode reading stuck
inline constexpr uint8_t kFaultPotStuck = 0x10;   // Fault flag: Potentiometer reading stuck

} // namespace kern::storage

