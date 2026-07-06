/*
Tests for KERN-LITE DSP and SensorRecord.

file: tests/host/test_dsp.cpp
author: Smallejoo
date: 2026-06-07
*/

#include "../../firmware/dsp/moving_average.hpp"
#include "../../firmware/dsp/threshold_detector.hpp"
#include "../../firmware/storage/sensor_record.hpp"
#include "../../firmware/protocol/crc32.hpp"

#include <cstdio>
#include <cmath>
#include <cstdint>
#include <cstddef>

static int g_failures = 0;

#define CHECK(cond) do { \
    if (!(cond)) { \
        std::printf("FAIL: %s line %d\n", #cond, __LINE__); \
        g_failures++; \
    } \
} while (0)

static bool near(float a, float b, float eps = 0.01f)
{
    return std::fabs(a - b) <= eps;
}

static void test_moving_average()
{
    kern::dsp::MovingAverage<float, 3> avg;

    const float input[] = {
        0.0f, 0.0f, 0.0f, 10.0f, 10.0f, 10.0f
    };

    const float expected[] = {
        0.0f, 0.0f, 0.0f, 3.33f, 6.67f, 10.0f
    };

    for (size_t i = 0; i < 6; ++i)
    {
        float out = avg.update(input[i]);
        CHECK(near(out, expected[i]));
    }

    std::printf("[OK] MovingAverage test done\n");
}

static void test_threshold_rising()
{
    kern::dsp::ThresholdConfig cfg{10.0f, 20.0f, 2.0f};
    kern::dsp::ThresholdDetector det(cfg);

    CHECK(det.state() == kern::dsp::ThresholdDetector::State::Normal);

    CHECK(det.update(21.0f) == kern::dsp::ThresholdDetector::State::HighAlert);

    // hi - hysteresis - epsilon = 20 - 2 - 0.1 = 17.9
    CHECK(det.update(17.9f) == kern::dsp::ThresholdDetector::State::Normal);

    std::printf("[OK] Threshold rising test done\n");
}

static void test_threshold_falling()
{
    kern::dsp::ThresholdConfig cfg{10.0f, 20.0f, 2.0f};
    kern::dsp::ThresholdDetector det(cfg);

    CHECK(det.state() == kern::dsp::ThresholdDetector::State::Normal);

    CHECK(det.update(9.0f) == kern::dsp::ThresholdDetector::State::LowAlert);

    // lo + hysteresis + epsilon = 10 + 2 + 0.1 = 12.1
    CHECK(det.update(12.1f) == kern::dsp::ThresholdDetector::State::Normal);

    std::printf("[OK] Threshold falling test done\n");
}

static void test_no_chatter()
{
    kern::dsp::ThresholdConfig cfg{10.0f, 20.0f, 2.0f};
    kern::dsp::ThresholdDetector det(cfg);

    CHECK(det.update(21.0f) == kern::dsp::ThresholdDetector::State::HighAlert);

    // exactly hi - hysteresis = 18.0
    // your detector clears only when value < hi - hysteresis
    // so exactly 18.0 should stay HighAlert
    for (int i = 0; i < 5; ++i)
    {
        CHECK(det.update(18.0f) == kern::dsp::ThresholdDetector::State::HighAlert);
    }

    std::printf("[OK] No chatter test done\n");
}

static void test_record_layout()
{
    static_assert(sizeof(kern::storage::SensorRecord) == 32,
                  "SensorRecord must be 32 bytes");

    static_assert(offsetof(kern::storage::SensorRecord, crc32) == 28,
                  "crc32 must be at offset 28");

    std::printf("[OK] SensorRecord layout test done\n");
}

static void test_record_crc()
{
    kern::storage::SensorRecord rec{};

    // all zeros except seq = 1
    rec.seq = 1;

    uint32_t crc = kern::protocol::crc32(
        reinterpret_cast<const uint8_t*>(&rec),
        offsetof(kern::storage::SensorRecord, crc32)
    );

    rec.crc32 = crc;

    uint32_t check = kern::protocol::crc32(
        reinterpret_cast<const uint8_t*>(&rec),
        offsetof(kern::storage::SensorRecord, crc32)
    );

    CHECK(check == rec.crc32);

    std::printf("[OK] Record CRC test done\n");
}

int main()
{
    test_moving_average();
    test_threshold_rising();
    test_threshold_falling();
    test_no_chatter();
    test_record_layout();
    test_record_crc();

    if (g_failures == 0)
    {
        std::printf("ALL DSP TESTS PASSED\n");
        return 0;
    }

    std::printf("%d TEST(S) FAILED\n", g_failures);
    return 1;
}
