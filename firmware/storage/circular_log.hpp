/*
 * CircularLog: multi-file ring buffer over FatFs with metadata persistence,
 * crash recovery, and replay.
 *
 * file: firmware/storage/circular_log.hpp
 * author: shalom2552
 * date: 2026-07-07
 */
#pragma once

#include "ff.h"
#include "../system/config.hpp"
#include "sensor_record.hpp"

#include "FreeRTOS.h"
#include "semphr.h"

#include <cstdint>

namespace kern::storage {

inline constexpr uint8_t  LOG_FILE_COUNT = config::kLogFileCount;
inline constexpr uint16_t RECORDS_PER_FILE = config::kRecordsPerFile;
inline constexpr uint16_t META_FLUSH_EVERY_N = config::kMetaFlushEveryN;
inline constexpr uint32_t ERASE_MAGIC = config::kEraseMagic;
inline constexpr uint32_t META_MAGIC = config::kMetaMagic;
inline constexpr uint32_t META_VERSION = config::kMetaVersion;

/*
 * @brief Metadata tracking log file indices, write pointers, and statistics.
 * Stored in META.BIN on the SD card to recover state across boots.
 */
#pragma pack(push, 1)
struct LogMeta {
    uint32_t magic;
    uint32_t version;
    uint8_t file_count;
    uint16_t records_per_file;
    uint8_t current_file;
    uint16_t write_index;
    uint32_t wrap_count;
    uint32_t total_records;
    uint8_t reserved[10]; // pad to 32 bytes before CRC
    uint32_t crc32;        // over all preceding bytes
};
#pragma pack(pop)

static_assert(sizeof(LogMeta) == 36, "LogMeta size");

/*
 * @brief Storage operation results.
 */
enum class StorageStatus : uint8_t {
    Ok,
    IoError,
    Corrupt,
    Full,
    BadMagic,
    NotMounted
};

// Callback function type invoked for each record during log replay.
using RecordCb = bool (*)(const SensorRecord&, void* ctx);

/*
 * @brief Multi-file circular logger managing data records on FatFs/SD storage.
 */
class CircularLog {
public:
    /*
     * @brief Mount the file system and initialize/recover log metadata.
     * @return StorageStatus indicating success or specific failure.
     * prepare the disk / SD card / file system for read and write
     */
    StorageStatus mount();

    /*
     * @brief Close open log files and run a fresh mount/recovery pass.
     * @return StorageStatus indicating success or specific failure.
     */
    StorageStatus remount();

    /*
     * @brief Write a sensor record to the circular log.
     * @param r The SensorRecord to write.
     * @return StorageStatus indicating success or failure.
     */
    StorageStatus writeRecord(const SensorRecord& r);

    /*
     * @brief Replay the newest N records, calling the callback for each.
     * @param n Maximum number of records to replay.
     * @param cb Callback function.
     * @param ctx User context pointer passed to callback.
     * @return StorageStatus indicating replay result.
     */
    StorageStatus replayNewest(uint32_t n, RecordCb cb, void* ctx);

    /*
     * @brief Erase all logs and reset metadata.
     * @param magic Must match ERASE_MAGIC to authorize erase.
     * @return StorageStatus indicating success or failure.
     */
    StorageStatus eraseAll(uint32_t magic);

    /*
     * @brief Flush current metadata to persistent storage.
     * @return StorageStatus indicating success or failure.
     */
    StorageStatus flushMeta();

    /*
     * @brief Get the total number of records written.
     * @return Total record count.
     */
    uint32_t totalRecords() const;

    /*
     * @brief Get the number of times the circular log wrapped around.
     * @return Wrap count.
     */
    uint32_t wrapCount() const;

    /*
     * @brief Get the index of the currently active log file.
     * @return File index.
     */
    uint8_t currentFile() const;

    /*
     * @brief Get the write index within the current active log file.
     * @return Write index.
     */
    uint16_t writeIndex() const;

    /*
     * @brief Check if the file system is currently mounted.
     * @return true if mounted.
     */
    bool isMounted() const;

private:
    friend class LogGuard;

    /*
     * @brief Mount body shared by mount/remount/eraseAll; caller must hold the mutex.
     * @return StorageStatus result.
     */
    StorageStatus mountLocked();

    /*
     * @brief Create the mutex on first use, then take it. Paired with unlock().
     */
    void lock();

    /*
     * @brief Release the mutex taken by lock().
     */
    void unlock();

    /*
     * @brief Read metadata from META.BIN and verify its integrity.
     * @return StorageStatus result.
     */
    StorageStatus readMeta();

    /*
     * @brief Write the metadata struct to META.BIN with updated CRC.
     * @return StorageStatus result.
     */
    StorageStatus writeMeta();

    /*
     * @brief Recover actual log write position if metadata is corrupt or missing.
     * @return StorageStatus result.
     */
    StorageStatus recoverPosition();

    /*
     * @brief Calculate the CRC32 of the LogMeta struct.
     * @param m The metadata struct.
     * @return Calculated CRC32.
     */
    uint32_t metaCrc(const LogMeta& m);

    /*
     * @brief Calculate the CRC32 of a SensorRecord struct.
     * @param r The SensorRecord struct.
     * @return Calculated CRC32.
     */
    uint32_t recordCrc(const SensorRecord& r);

private:
    FATFS m_fatfs{};
    FIL m_files[LOG_FILE_COUNT]{};
    bool m_filesOpen[LOG_FILE_COUNT]{};
    LogMeta m_meta{};
    bool m_mounted = false;

    // Serializes writeRecord/replayNewest/eraseAll/flushMeta across tasks;
    // FatFs re-entrancy only locks single f_* calls, not seek+write sequences.
    StaticSemaphore_t m_mutexStorage{};
    SemaphoreHandle_t m_mutex = nullptr;
};

} // namespace kern::storage

