// Standalone host test: no STM32 headers. Compile against
// firmware/protocol/crc32.* and firmware/protocol/codec.* only.
#include "../../firmware/protocol/crc32.hpp"
#include "../../firmware/protocol/codec.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

using namespace kern::protocol;

static int g_failures = 0;
#define CHECK(cond) do { \
    if (!(cond)) { \
        std::printf("FAIL: %s (line %d)\n", #cond, __LINE__); \
        g_failures++; \
    } \
} while (0)

static void test_crc_kat() {
    const uint8_t vec[] = "123456789";
    uint32_t c = crc32(vec, 9);
    CHECK(c == 0xCBF43926u);
    if (c != 0xCBF43926u) {
        std::printf("BLOCKER: CRC KAT failed (got 0x%08X). Stop and fix CRC params.\n", c);
    }
}

static void roundtrip(FrameType type, const uint8_t* payload, uint16_t len) {
    Frame f{};
    f.type = type;
    f.len = len;
    if (len > 0) std::memcpy(f.payload, payload, len);

    uint8_t buf[kMaxFrameSize];
    size_t n = encode(f, buf, sizeof(buf));
    CHECK(n == kFrameOverhead + len);

    Decoder dec;
    DecodeResult r = DecodeResult::NeedMore;
    for (size_t i = 0; i < n; ++i) {
        r = dec.feed(buf[i]);
    }
    CHECK(r == DecodeResult::FrameReady);
    CHECK(dec.frame().type == type);
    CHECK(dec.frame().len == len);
    CHECK(std::memcmp(dec.frame().payload, payload, len) == 0);
}

static void test_roundtrip_status14() {
    uint8_t payload[14] = {0,1,4,0, 0,0,0,0, 0,0,0,0, 0,0};
    roundtrip(FrameType::Status, payload, 14);
}

static void test_roundtrip_ack_empty() {
    roundtrip(FrameType::Ack, nullptr, 0);
}

static void test_roundtrip_max_payload() {
    uint8_t payload[256];
    for (int i = 0; i < 256; ++i) payload[i] = static_cast<uint8_t>(i);
    roundtrip(FrameType::Record, payload, 256);
}

static void test_corruption_detected() {
    uint8_t payload[14] = {0,1,4,0, 0,0,0,0, 0,0,0,0, 0,0};
    Frame f{};
    f.type = FrameType::Status;
    f.len = 14;
    std::memcpy(f.payload, payload, 14);

    uint8_t buf[kMaxFrameSize];
    size_t n = encode(f, buf, sizeof(buf));

    // Flip a payload byte (payload starts at offset 4).
    buf[4 + 5] ^= 0xFF;

    Decoder dec;
    DecodeResult r = DecodeResult::NeedMore;
    for (size_t i = 0; i < n; ++i) r = dec.feed(buf[i]);
    CHECK(r == DecodeResult::CrcError);
}

static void test_resync_after_garbage() {
    Frame f{};
    f.type = FrameType::Ack;
    f.len = 0;

    uint8_t buf[kMaxFrameSize];
    size_t n = encode(f, buf, sizeof(buf));

    Decoder dec;
    DecodeResult r = DecodeResult::NeedMore;
    // 12 garbage bytes first.
    for (int i = 0; i < 12; ++i) {
        r = dec.feed(static_cast<uint8_t>(0x55 + i));
        CHECK(r == DecodeResult::NeedMore);
    }
    for (size_t i = 0; i < n; ++i) r = dec.feed(buf[i]);
    CHECK(r == DecodeResult::FrameReady);

}

static void test_oversized_len_syncs() {
    Decoder dec;
    DecodeResult r;
    r = dec.feed(kStx);          CHECK(r == DecodeResult::NeedMore);
    r = dec.feed(0x10);          CHECK(r == DecodeResult::NeedMore); // TYPE = Record
    r = dec.feed(0xFF);          CHECK(r == DecodeResult::NeedMore); // LEN_LO
    r = dec.feed(0x01);          CHECK(r == DecodeResult::SyncError); // LEN = 511 > 256

    // Decoder must recover: a valid frame right after must still decode.
    Frame f{};
    f.type = FrameType::Ack;
    f.len = 0;
    uint8_t buf[kMaxFrameSize];
    size_t n = encode(f, buf, sizeof(buf));
    for (size_t i = 0; i < n; ++i) r = dec.feed(buf[i]);
    CHECK(r == DecodeResult::FrameReady);
}

int main() {
    test_crc_kat();
    test_roundtrip_status14();
    test_roundtrip_ack_empty();
    test_roundtrip_max_payload();
    test_corruption_detected();
    test_resync_after_garbage();
    test_oversized_len_syncs();

    if (g_failures == 0) {
        std::printf("ALL TESTS PASSED\n");
        return 0;
    }
    std::printf("%d TEST(S) FAILED\n", g_failures);
    return 1;
}


