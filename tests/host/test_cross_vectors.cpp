#include "../../firmware/protocol/codec.hpp"

#include <cstdio>
#include <cstdint>
#include <cstddef>

using namespace kern::protocol;

static int g_failures = 0;

#define CHECK(cond) do { \
    if (!(cond)) { \
        std::printf("FAIL: %s line %d\n", #cond, __LINE__); \
        g_failures++; \
    } \
} while (0)

static DecodeResult feed_all(Decoder& dec, const uint8_t* data, size_t len)
{
    DecodeResult r = DecodeResult::NeedMore;

    for (size_t i = 0; i < len; ++i)
    {
        r = dec.feed(data[i]);
    }

    return r;
}

static void test_vector(const char* name,
                        const uint8_t* data,
                        size_t len,
                        FrameType expectedType,
                        uint16_t expectedLen)
{
    Decoder dec;
    DecodeResult r = feed_all(dec, data, len);

    CHECK(r == DecodeResult::FrameReady);
    CHECK(dec.frame().type == expectedType);
    CHECK(dec.frame().len == expectedLen);

    std::printf("[OK] %s decoded\n", name);
}

int main()
{
    const uint8_t ACK_VECTOR[] = {
        0xAB, 0x20, 0x00, 0x00,
        0xF2, 0x9F, 0x0C, 0xC7,
        0xCD
    };

    const uint8_t STATUS14_VECTOR[] = {
        0xAB, 0x12, 0x0E, 0x00,
        0x00, 0x01, 0x04, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00,
        0x56, 0xEC, 0x90, 0xF4,
        0xCD
    };

    const uint8_t RECORD32_VECTOR[] = {
        0xAB, 0x10, 0x20, 0x00,
        0x00, 0x01, 0x02, 0x03,
        0x04, 0x05, 0x06, 0x07,
        0x08, 0x09, 0x0A, 0x0B,
        0x0C, 0x0D, 0x0E, 0x0F,
        0x10, 0x11, 0x12, 0x13,
        0x14, 0x15, 0x16, 0x17,
        0x18, 0x19, 0x1A, 0x1B,
        0x1C, 0x1D, 0x1E, 0x1F,
        0x1D, 0x0B, 0x42, 0x85,
        0xCD
    };

    test_vector("ACK_VECTOR", ACK_VECTOR, sizeof(ACK_VECTOR), FrameType::Ack, 0);
    test_vector("STATUS14_VECTOR", STATUS14_VECTOR, sizeof(STATUS14_VECTOR), FrameType::Status, 14);
    test_vector("RECORD32_VECTOR", RECORD32_VECTOR, sizeof(RECORD32_VECTOR), FrameType::Record, 32);

    if (g_failures == 0)
    {
        std::printf("ALL C++ CROSS VECTOR TESTS PASSED\n");
        return 0;
    }

    std::printf("%d TEST(S) FAILED\n", g_failures);
    return 1;
}
