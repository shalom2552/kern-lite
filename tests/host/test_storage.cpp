/*
Host tests for kern::storage::CircularLog. Uses the FatFs shim in
tests/host/fatfs_shim to back the ring with regular files. Exercises index math,
file advance, wraparound, replay, erase, meta CRC, and crash recovery.

file: tests/host/test_storage.cpp
author: shalom2552
date: 2026-07-07
*/

// White-box access to private helpers/state (host test only).
#define private public
#include "../../firmware/storage/circular_log.hpp"
#undef private

#include "../../firmware/protocol/crc32.hpp"
#include "fatfs_shim/ff.h"

#include <cstdio>
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <vector>

using kern::storage::CircularLog;
using kern::storage::SensorRecord;
using kern::storage::StorageStatus;
using kern::storage::LOG_FILE_COUNT;
using kern::storage::RECORDS_PER_FILE;

static constexpr uint32_t CAP = static_cast<uint32_t>(LOG_FILE_COUNT) * RECORDS_PER_FILE;

static int g_failures = 0;

#define CHECK(cond) do { \
    if (!(cond)) { \
        std::printf("FAIL: %s line %d\n", #cond, __LINE__); \
        g_failures++; \
    } \
} while (0)

// ---- helpers ---------------------------------------------------------------

static void freshRoot(const char* name)
{
    char dir[256];
    std::snprintf(dir, sizeof(dir), "./_ffroot_%s", name);
    ff_test_set_root(dir);
    f_unlink("0:LOG00.BIN");
    f_unlink("0:LOG01.BIN");
    f_unlink("0:LOG02.BIN");
    f_unlink("0:LOG03.BIN");
    f_unlink("0:META.BIN");
}

// Build a record identifiable by seq. timestamp mirrors seq so ordering is
// strictly monotonic across the whole run.
static SensorRecord makeRecord(uint16_t seq)
{
    SensorRecord r{};
    r.timestamp = seq;
    r.ms = 0;
    r.seq = seq;
    r.light = seq;
    return r;
}

static bool crcValid(const SensorRecord& r)
{
    uint32_t c = kern::protocol::crc32(
        reinterpret_cast<const uint8_t*>(&r), offsetof(SensorRecord, crc32));
    return c == r.crc32;
}

struct Collector {
    std::vector<SensorRecord> recs;
};

static bool collect(const SensorRecord& r, void* ctx)
{
    static_cast<Collector*>(ctx)->recs.push_back(r);
    return true;
}

static void writeN(CircularLog& log, uint16_t from, uint16_t count)
{
    for (uint16_t i = 0; i < count; ++i) {
        log.writeRecord(makeRecord(static_cast<uint16_t>(from + i)));
    }
}

// ---- tests -----------------------------------------------------------------

static void test_file_advance()
{
    freshRoot("advance");
    CircularLog log;
    CHECK(log.mount() == StorageStatus::Ok);

    writeN(log, 1, RECORDS_PER_FILE); // exactly one file

    CHECK(log.currentFile() == 1);
    CHECK(log.writeIndex() == 0);
    CHECK(log.wrapCount() == 0);
    std::printf("[OK] file advance\n");
}

static void test_full_wrap()
{
    freshRoot("wrap");
    CircularLog log;
    CHECK(log.mount() == StorageStatus::Ok);

    writeN(log, 1, static_cast<uint16_t>(CAP)); // fill the whole ring once

    CHECK(log.wrapCount() == 1);
    CHECK(log.currentFile() == 0);
    CHECK(log.writeIndex() == 0);
    std::printf("[OK] full wrap\n");
}

static void test_overwrite_oldest()
{
    freshRoot("overwrite");
    CircularLog log;
    CHECK(log.mount() == StorageStatus::Ok);

    writeN(log, 1, static_cast<uint16_t>(CAP)); // seq 1..1024
    log.writeRecord(makeRecord(1025));          // overwrites file0 slot0 (seq 1)

    // Newest record is the one just written.
    Collector c;
    CHECK(log.replayNewest(1, collect, &c) == StorageStatus::Ok);
    CHECK(c.recs.size() == 1);
    CHECK(c.recs[0].seq == 1025);

    // Oldest retained is now seq 2 (seq 1 was overwritten).
    Collector all;
    CHECK(log.replayNewest(CAP, collect, &all) == StorageStatus::Ok);
    CHECK(all.recs.size() == CAP);
    CHECK(all.recs.front().seq == 2);
    CHECK(all.recs.back().seq == 1025);
    std::printf("[OK] overwrite oldest\n");
}

static void test_replay_no_wrap()
{
    freshRoot("replay10");
    CircularLog log;
    CHECK(log.mount() == StorageStatus::Ok);

    writeN(log, 1, 15);

    Collector c;
    CHECK(log.replayNewest(10, collect, &c) == StorageStatus::Ok);
    CHECK(c.recs.size() == 10);
    CHECK(c.recs.front().seq == 6);
    CHECK(c.recs.back().seq == 15);
    for (size_t i = 0; i < c.recs.size(); ++i) {
        CHECK(crcValid(c.recs[i]));
        if (i > 0) {
            CHECK(c.recs[i].seq > c.recs[i - 1].seq); // chronological
        }
    }
    std::printf("[OK] replay no wrap\n");
}

static void test_replay_clamp()
{
    freshRoot("replay400");
    CircularLog log;
    CHECK(log.mount() == StorageStatus::Ok);

    writeN(log, 1, 300);

    Collector c;
    CHECK(log.replayNewest(400, collect, &c) == StorageStatus::Ok);
    CHECK(c.recs.size() == 300); // clamped to total_records
    CHECK(c.recs.front().seq == 1);
    CHECK(c.recs.back().seq == 300);
    std::printf("[OK] replay clamp\n");
}

static void test_replay_across_boundary()
{
    freshRoot("boundary");
    CircularLog log;
    CHECK(log.mount() == StorageStatus::Ok);

    // 261 records => current_file=1, write_index=5.
    writeN(log, 1, static_cast<uint16_t>(RECORDS_PER_FILE + 5));
    CHECK(log.currentFile() == 1);
    CHECK(log.writeIndex() == 5);

    // replayNewest(20) spans file0 slots 241..255 then file1 slots 0..4.
    Collector c;
    CHECK(log.replayNewest(20, collect, &c) == StorageStatus::Ok);
    CHECK(c.recs.size() == 20);
    CHECK(c.recs.front().seq == 242); // global slot 241 -> seq 242
    CHECK(c.recs.back().seq == 261);  // global slot 260 -> seq 261
    for (size_t i = 1; i < c.recs.size(); ++i) {
        CHECK(c.recs[i].seq == c.recs[i - 1].seq + 1);
    }
    std::printf("[OK] replay across boundary\n");
}

static void test_erase_bad_magic()
{
    freshRoot("erase");
    CircularLog log;
    CHECK(log.mount() == StorageStatus::Ok);
    writeN(log, 1, 20);

    uint32_t before = log.totalRecords();
    CHECK(log.eraseAll(0x00000000u) == StorageStatus::BadMagic);
    CHECK(log.totalRecords() == before); // state unchanged
    CHECK(log.isMounted());
    std::printf("[OK] erase bad magic\n");
}

static void test_meta_crc()
{
    freshRoot("metacrc");
    CircularLog log;
    CHECK(log.mount() == StorageStatus::Ok);

    writeN(log, 1, 20);      // meta flushed along the way
    CHECK(log.writeMeta() == StorageStatus::Ok);
    CHECK(log.readMeta() == StorageStatus::Ok);

    // Corrupt one payload byte (not magic/version): CRC check must fail.
    FILE* f = std::fopen(ff_test_path("0:META.BIN"), "r+b");
    CHECK(f != nullptr);
    std::fseek(f, 12, SEEK_SET); // inside current_file/write_index region
    int b = std::fgetc(f);
    std::fseek(f, 12, SEEK_SET);
    std::fputc(b ^ 0xFF, f);
    std::fclose(f);

    CHECK(log.readMeta() == StorageStatus::Corrupt);
    std::printf("[OK] meta crc\n");
}

static void test_catchup_stale_meta()
{
    freshRoot("catchup");

    // 20 records: meta flushed at 16, slots 16..19 newer than the checkpoint.
    {
        CircularLog w;
        CHECK(w.mount() == StorageStatus::Ok);
        writeN(w, 1, 20);
    }

    CircularLog r;
    CHECK(r.mount() == StorageStatus::Ok);
    CHECK(r.totalRecords() == 20);
    CHECK(r.writeIndex() == 20);

    // "Reboot": seq and timestamp restart; write a new generation.
    writeN(r, 1, 5); // slots 20..24, meta on disk still at the old checkpoint

    CircularLog r2;
    CHECK(r2.mount() == StorageStatus::Ok);
    // Catch-up follows the seq chain 17..20 and stops at the generation
    // boundary. Loss is bounded by META_FLUSH_EVERY_N; gen-1 records intact.
    CHECK(r2.totalRecords() == 20);
    CHECK(r2.writeIndex() == 20);
    CHECK(r2.currentFile() == 0);

    Collector c;
    CHECK(r2.replayNewest(4, collect, &c) == StorageStatus::Ok);
    CHECK(c.recs.size() == 4);
    CHECK(c.recs[0].seq == 17);
    CHECK(c.recs[3].seq == 20);
    std::printf("[OK] catch-up stale meta\n");
}

static void test_recovery_position()
{
    freshRoot("recover");

    // Write 39 records (global slots 0..38), then wreck slot 38 and drop meta.
    {
        CircularLog w;
        CHECK(w.mount() == StorageStatus::Ok);
        writeN(w, 1, 39);
    }

    // Overwrite the 39th record (slot 38) with garbage so its CRC is invalid.
    FILE* f = std::fopen(ff_test_path("0:LOG00.BIN"), "r+b");
    CHECK(f != nullptr);
    std::fseek(f, 38 * static_cast<long>(sizeof(SensorRecord)), SEEK_SET);
    for (size_t i = 0; i < sizeof(SensorRecord); ++i) {
        std::fputc(0xFF, f);
    }
    std::fclose(f);

    // Drop metadata so mount() must fall back to a full recoverPosition() scan.
    f_unlink("0:META.BIN");

    CircularLog r;
    CHECK(r.mount() == StorageStatus::Ok);
    CHECK(r.currentFile() == 0);
    CHECK(r.writeIndex() == 38); // last valid record was slot 37 -> head 38
    CHECK(r.wrapCount() == 0);
    CHECK(r.totalRecords() == 38);
    std::printf("[OK] recovery position\n");
}

int main()
{
    test_file_advance();
    test_full_wrap();
    test_overwrite_oldest();
    test_replay_no_wrap();
    test_replay_clamp();
    test_replay_across_boundary();
    test_erase_bad_magic();
    test_meta_crc();
    test_catchup_stale_meta();
    test_recovery_position();

    if (g_failures == 0) {
        std::printf("ALL STORAGE TESTS PASSED\n");
        return 0;
    }
    std::printf("%d TEST(S) FAILED\n", g_failures);
    return 1;
}
