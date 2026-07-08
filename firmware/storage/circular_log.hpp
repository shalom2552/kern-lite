/*
CircularLog: multi-file ring buffer over FatFs with metadata persistence,
crash recovery, and replay.

file: firmware/storage/circular_log.hpp
author: shalom2552
date: 2026-07-07
*/

#pragma once

#include "sensor_record.hpp"
#include "ff.h"

#include <cstdint>

namespace kern::storage {

inline constexpr uint8_t LOG_FILE_COUNT = 4;
inline constexpr uint16_t RECORDS_PER_FILE = 256;
inline constexpr uint16_t META_FLUSH_EVERY_N = 16;
inline constexpr uint32_t ERASE_MAGIC = 0xDEADC0DEu;
inline constexpr uint32_t META_MAGIC = 0x4C4F4700u; // "LOG\0"
inline constexpr uint32_t META_VERSION = 1u;

#pragma pack(push, 1)
struct LogMeta { // stored in META.BIN
    uint32_t magic;
    uint32_t version;
    // how many files we use to save data
    uint8_t file_count;
    // per file how much records we got
    uint16_t records_per_file;
    uint8_t current_file;
    uint16_t write_index;
    // how much times did we start from the begining and overwrited old records
    uint32_t wrap_count;
    uint32_t total_records;
    uint8_t reserved[10]; // pad to 32 bytes before CRC
    uint32_t crc32;        // over all preceding bytes
};

#pragma pack(pop)

static_assert(sizeof(LogMeta) == 36, "LogMeta size");

enum class StorageStatus : uint8_t { Ok, IoError, Corrupt, Full, BadMagic, NotMounted };

using RecordCb = bool (*)(const SensorRecord&, void* ctx);

class CircularLog {
public:
	//prepare the disk / SD card / file system for read and write
    StorageStatus mount();
    StorageStatus writeRecord(const SensorRecord& r);
    StorageStatus replayNewest(uint32_t n, RecordCb cb, void* ctx);
    StorageStatus eraseAll(uint32_t magic);

    uint32_t totalRecords() const;
    uint32_t wrapCount() const;
    uint8_t currentFile() const;
    uint16_t writeIndex() const;
    bool isMounted() const;

private:
    StorageStatus readMeta();
    StorageStatus writeMeta();
    StorageStatus recoverPosition();
    uint32_t metaCrc(const LogMeta& m);
    uint32_t recordCrc(const SensorRecord& r);

    FATFS m_fatfs{};
    FIL m_files[LOG_FILE_COUNT]{};
    bool m_filesOpen[LOG_FILE_COUNT]{};
    LogMeta m_meta{};
    bool m_mounted = false;
};

} // namespace kern::storage
