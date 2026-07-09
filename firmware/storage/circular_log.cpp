/*
CircularLog implementation: sequential write across a ring of FatFs files,
metadata persistence with CRC, crash recovery, and newest-first replay.

file: firmware/storage/circular_log.cpp
author: shalom2552
date: 2026-07-07
*/

#include "circular_log.hpp"

#include "../protocol/crc32.hpp"

#include <cstddef>
#include <cstring>

namespace kern::storage {

static constexpr uint32_t kRecordSize = sizeof(SensorRecord);
static constexpr uint32_t kCapacity = static_cast<uint32_t>(LOG_FILE_COUNT) * RECORDS_PER_FILE;
static constexpr const char* kMetaPath = "0:META.BIN";

// 8.3 file names on volume 0. Index maps to LOG0N.BIN.
static const char* logPath(uint8_t file)
{
    // The FatFs volume uses a fixed ring of numbered files, so map the slot
    // index directly to the corresponding 8.3 file name.
    static const char names[LOG_FILE_COUNT][12] = {
        "0:LOG00.BIN", "0:LOG01.BIN", "0:LOG02.BIN", "0:LOG03.BIN"
    };
    return names[file];
}

// Ordering key for "which record is newest": timestamp, then ms, then seq.
// Returns true when a is strictly newer than b.
static bool newer(const SensorRecord& a, const SensorRecord& b)
{
    // Compare timestamps first, then ms, then sequence to reconstruct order
    // even when several records share the same coarse timestamp.
    if (a.timestamp != b.timestamp) return a.timestamp > b.timestamp;
    if (a.ms != b.ms) return a.ms > b.ms;
    return a.seq > b.seq;
}

uint32_t CircularLog::recordCrc(const SensorRecord& r)
{
    return kern::protocol::crc32(
        reinterpret_cast<const uint8_t*>(&r), offsetof(SensorRecord, crc32));
}

uint32_t CircularLog::metaCrc(const LogMeta& m)
{
    return kern::protocol::crc32(
        reinterpret_cast<const uint8_t*>(&m), offsetof(LogMeta, crc32));
}

StorageStatus CircularLog::readMeta()
{
    // Metadata is optional only on a clean system; if it exists, verify it
    // before trusting the saved write head and wrap counters.
    FIL f{};
    if (f_open(&f, kMetaPath, FA_READ) != FR_OK) {
        return StorageStatus::Corrupt;
    }
    LogMeta m{};
    UINT br = 0;
    FRESULT fr = f_read(&f, &m, sizeof(m), &br);
    f_close(&f);
    if (fr != FR_OK || br != sizeof(m)) {
        return StorageStatus::Corrupt;
    }
    if (m.magic != META_MAGIC || m.version != META_VERSION) {
        return StorageStatus::Corrupt;
    }
    if (metaCrc(m) != m.crc32) {
        return StorageStatus::Corrupt;
    }
    m_meta = m;
    return StorageStatus::Ok;
}

StorageStatus CircularLog::writeMeta()
{
    // Persist the ring state after every successful write so recovery can
    // resume from the last known head instead of scanning from scratch.
    m_meta.magic = META_MAGIC;
    m_meta.version = META_VERSION;
    m_meta.file_count = LOG_FILE_COUNT;
    m_meta.records_per_file = RECORDS_PER_FILE;
    m_meta.crc32 = metaCrc(m_meta);

    FIL f{};
    if (f_open(&f, kMetaPath, FA_WRITE | FA_CREATE_ALWAYS) != FR_OK) {
        return StorageStatus::IoError;
    }
    UINT bw = 0;
    FRESULT fr = f_write(&f, &m_meta, sizeof(m_meta), &bw);
    if (fr == FR_OK) {
        f_sync(&f);
    }
    f_close(&f);
    if (fr != FR_OK || bw != sizeof(m_meta)) {
        return StorageStatus::IoError;
    }
    return StorageStatus::Ok;
}

// Read one record from a circular slot. A slot past EOF is unwritten: return a
// zeroed record (CRC fails) instead of expanding the file. False on I/O error.
static bool readSlot(FIL* files, uint32_t globalPos, SensorRecord& out)
{
    // A slot beyond the file size is treated as unwritten, which keeps the
    // scan logic simple and avoids expanding sparse files during recovery.
    uint8_t file = static_cast<uint8_t>(globalPos / RECORDS_PER_FILE);
    uint16_t idx = static_cast<uint16_t>(globalPos % RECORDS_PER_FILE);
    FIL* fp = &files[file];
    FSIZE_t off = static_cast<FSIZE_t>(idx) * kRecordSize;
    if (f_size(fp) < off + kRecordSize) {
        std::memset(&out, 0, sizeof(out));
        return true; // unwritten slot
    }
    if (f_lseek(fp, off) != FR_OK) {
        return false;
    }
    UINT br = 0;
    if (f_read(fp, &out, kRecordSize, &br) != FR_OK || br != kRecordSize) {
        return false;
    }
    return true;
}

StorageStatus CircularLog::recoverPosition()
{
    // Full scan: reset header fields, keep counters zeroed, then locate the
    // newest valid record across every slot.
    std::memset(&m_meta, 0, sizeof(m_meta));

    SensorRecord rec{};
    SensorRecord newestRec{};
    bool haveNewest = false;
    int64_t newestPos = -1;
    uint32_t validCount = 0;

    for (uint32_t pos = 0; pos < kCapacity; ++pos) {
        if (!readSlot(m_files, pos, rec)) {
            return StorageStatus::IoError;
        }
        if (recordCrc(rec) != rec.crc32) {
            continue; // empty or corrupt slot
        }
        ++validCount;
        if (!haveNewest || newer(rec, newestRec)) {
            newestRec = rec;
            newestPos = static_cast<int64_t>(pos);
            haveNewest = true;
        }
    }

    if (!haveNewest) {
        // Nothing recoverable; leave counters at zero (fresh ring).
        return StorageStatus::Ok;
    }

    // Head is the slot after the newest record. A completely full ring (every
    // slot valid) has wrapped at least once; otherwise the valid records are the
    // contiguous prefix and no wrap has occurred.
    uint32_t head = static_cast<uint32_t>((newestPos + 1) % kCapacity);
    bool wrapped = (validCount == kCapacity);
    m_meta.wrap_count = wrapped ? 1u : 0u;
    m_meta.total_records = m_meta.wrap_count * kCapacity + head;
    m_meta.current_file = static_cast<uint8_t>(head / RECORDS_PER_FILE);
    m_meta.write_index = static_cast<uint16_t>(head % RECORDS_PER_FILE);
    return StorageStatus::Ok;
}

// Advance the write head one slot, rolling files and wrap_count as needed.
static void advanceHead(LogMeta& meta)
{
    ++meta.write_index;
    if (meta.write_index == RECORDS_PER_FILE) {
        meta.write_index = 0;
        meta.current_file = static_cast<uint8_t>((meta.current_file + 1) % LOG_FILE_COUNT);
        if (meta.current_file == 0) {
            ++meta.wrap_count;
        }
    }
}

StorageStatus CircularLog::mount()
{
    // Mount the filesystem, open all ring files, then restore the write head
    // from metadata or by scanning the records if metadata is unavailable.
    if (f_mount(&m_fatfs, "0:", 1) != FR_OK) {
        return StorageStatus::IoError;
    }

    for (uint8_t i = 0; i < LOG_FILE_COUNT; ++i) {
        if (f_open(&m_files[i], logPath(i), FA_READ | FA_WRITE | FA_OPEN_ALWAYS) != FR_OK) {
            return StorageStatus::IoError;
        }
        m_filesOpen[i] = true;
    }

    if (readMeta() == StorageStatus::Ok) {
        // Valid metadata: recover any records written since the last flush by
        // scanning forward from the saved head while records stay monotonic.
        uint32_t head = static_cast<uint32_t>(m_meta.current_file) * RECORDS_PER_FILE
                        + m_meta.write_index;

        SensorRecord prev{};
        bool havePrev = false;
        if (m_meta.total_records > 0) {
            SensorRecord last{};
            uint32_t lastPos = (head + kCapacity - 1) % kCapacity;
            if (readSlot(m_files, lastPos, last) && recordCrc(last) == last.crc32) {
                prev = last;
                havePrev = true;
            }
        }

        SensorRecord rec{};
        for (uint32_t step = 0; step < kCapacity; ++step) {
            if (!readSlot(m_files, head, rec)) {
                return StorageStatus::IoError;
            }
            if (recordCrc(rec) != rec.crc32) {
                break; // no more written records
            }
            if (havePrev && !newer(rec, prev)) {
                break; // older record from a previous generation
            }
            advanceHead(m_meta);
            ++m_meta.total_records;
            prev = rec;
            havePrev = true;
            head = static_cast<uint32_t>(m_meta.current_file) * RECORDS_PER_FILE
                   + m_meta.write_index;
        }
    } else {
        // Corrupt or unreadable metadata: full scan to rebuild position.
        StorageStatus rst = recoverPosition();
        if (rst != StorageStatus::Ok) {
            return rst;
        }
    }

    if (m_meta.total_records == 0 && m_meta.wrap_count == 0) {
        // Fresh (or empty) ring: persist zeroed metadata.
        std::memset(&m_meta, 0, sizeof(m_meta));
        StorageStatus wst = writeMeta();
        if (wst != StorageStatus::Ok) {
            return wst;
        }
    }

    m_mounted = true;
    return StorageStatus::Ok;
}

StorageStatus CircularLog::writeRecord(const SensorRecord& r)
{
    if (!m_mounted) {
        return StorageStatus::NotMounted;
    }

    // Copy the record, stamp its CRC, and write it into the current ring slot.
    SensorRecord stored = r;
    stored.crc32 = recordCrc(stored);

    FIL* fp = &m_files[m_meta.current_file];
    if (f_lseek(fp, static_cast<FSIZE_t>(m_meta.write_index) * kRecordSize) != FR_OK) {
        return StorageStatus::IoError;
    }
    UINT bw = 0;
    FRESULT fr = f_write(fp, &stored, kRecordSize, &bw);
    if (fr != FR_OK || bw != kRecordSize) {
        return StorageStatus::IoError;
    }
    f_sync(fp); // persist for crash recovery

    advanceHead(m_meta);
    ++m_meta.total_records;

    if (m_meta.total_records % META_FLUSH_EVERY_N == 0) {
        return writeMeta();
    }
    return StorageStatus::Ok;
}

StorageStatus CircularLog::replayNewest(uint32_t n, RecordCb cb, void* ctx)
{
    if (!m_mounted) {
        return StorageStatus::NotMounted;
    }

    uint32_t retained = m_meta.total_records < kCapacity ? m_meta.total_records : kCapacity;
    if (n > retained) {
        n = retained;
    }
    if (n == 0) {
        return StorageStatus::Ok;
    }

    uint32_t head = static_cast<uint32_t>(m_meta.current_file) * RECORDS_PER_FILE
                    + m_meta.write_index;
    uint32_t start = (head - n + kCapacity) % kCapacity;

    StorageStatus result = StorageStatus::Ok;
    SensorRecord rec{};
    for (uint32_t i = 0; i < n; ++i) {
        uint32_t pos = (start + i) % kCapacity;
        if (!readSlot(m_files, pos, rec)) {
            return StorageStatus::IoError;
        }
        if (recordCrc(rec) != rec.crc32) {
            // Deliver the raw record anyway so the GS can report corruption.
            result = StorageStatus::Corrupt;
        }
        if (!cb(rec, ctx)) {
            break;
        }
    }
    return result;
}

StorageStatus CircularLog::eraseAll(uint32_t magic)
{
    if (magic != ERASE_MAGIC) {
        return StorageStatus::BadMagic;
    }

    for (uint8_t i = 0; i < LOG_FILE_COUNT; ++i) {
        if (m_filesOpen[i]) {
            f_close(&m_files[i]);
            m_filesOpen[i] = false;
        }
    }
    for (uint8_t i = 0; i < LOG_FILE_COUNT; ++i) {
        f_unlink(logPath(i));
    }
    f_unlink(kMetaPath);

    m_mounted = false;
    return mount();
}

StorageStatus CircularLog::flushMeta()
{
    if (!m_mounted) {
        return StorageStatus::NotMounted;
    }
    return writeMeta();
}

uint32_t CircularLog::totalRecords() const { return m_meta.total_records; }
uint32_t CircularLog::wrapCount() const { return m_meta.wrap_count; }
uint8_t CircularLog::currentFile() const { return m_meta.current_file; }
uint16_t CircularLog::writeIndex() const { return m_meta.write_index; }
bool CircularLog::isMounted() const { return m_mounted; }

} // namespace kern::storage
