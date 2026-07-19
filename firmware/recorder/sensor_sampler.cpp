/*
 * SensorSampler implementation: sensor reads, DSP filtering, alert/fault bit
 * packing, and SensorRecord assembly.
 *
 * file: firmware/recorder/sensor_sampler.cpp
 * author: shalom2552
 * date: 2026-07-14
 */
#include "sensor_sampler.hpp"

#include "../dsp/threshold_detector.hpp"
#include "../protocol/crc32.hpp"

#include <cstddef>

namespace kern::recorder {

namespace {

constexpr uint32_t DHT_SAMPLE_EVERY_N_TICKS = 20;

// Alert bits are packed exactly like the host decoder expects.
constexpr uint8_t kAlertLm35High = 0x01;
constexpr uint8_t kAlertLm35Low = 0x02;
constexpr uint8_t kAlertLightHigh = 0x04;
constexpr uint8_t kAlertLightLow = 0x08;
constexpr uint8_t kAlertPotHigh = 0x10;
constexpr uint8_t kAlertPotLow = 0x20;
constexpr uint8_t kAlertDhtTempHigh = 0x40;
constexpr uint8_t kAlertDhtHumHigh = 0x80;

uint8_t alertMask(kern::dsp::ThresholdDetector::State alert, uint8_t highBit, uint8_t lowBit)
{
    using kern::dsp::ThresholdDetector;

    if (alert == ThresholdDetector::State::HighAlert) {
        return highBit;
    }
    if (alert == ThresholdDetector::State::LowAlert) {
        return lowBit;
    }
    return 0u;
}

} // namespace

SensorSampler::SensorSampler(ADC_HandleTypeDef* adc)
    : m_lm35(adc)
    , m_photo(adc)
    , m_pot(adc)
{
}

void SensorSampler::init()
{
    m_lm35.init();
    m_dht11.init();
    m_latch.init();
    m_photo.init();
    m_pot.init();
}

void SensorSampler::sampleAnalogSensors(kern::storage::SensorRecord& rec,
                                        uint8_t& alertBits, uint8_t& faultBits)
{
    // Range checks map directly to the fault bit layout used by telemetry.py.
    float lm35Temp = m_lm35.readCelsius();
    auto lm35Out = m_chLm35.process(lm35Temp);
    rec.lm35_c = static_cast<int16_t>(lm35Out.filtered * 10.0f);
    alertBits |= alertMask(lm35Out.alert, kAlertLm35High, kAlertLm35Low);
    if (lm35Temp < -10.0f || lm35Temp > 100.0f) {
        faultBits |= kern::storage::kFaultLm35Range;
    }

    float lightRaw = m_photo.readNormalized();
    auto photoOut = m_chPhoto.process(lightRaw);
    rec.light = static_cast<uint16_t>(photoOut.filtered * 65535.0f);
    alertBits |= alertMask(photoOut.alert, kAlertLightHigh, kAlertLightLow);
    if (lightRaw <= 0.001f || lightRaw >= 0.999f) {
        faultBits |= kern::storage::kFaultLightStuck;
    }

    float potRaw = m_pot.readNormalized();
    auto potOut = m_chPot.process(potRaw);
    rec.pot = static_cast<uint16_t>(potOut.filtered * 65535.0f);
    alertBits |= alertMask(potOut.alert, kAlertPotHigh, kAlertPotLow);
    if (potRaw <= 0.001f || potRaw >= 0.999f) {
        faultBits |= kern::storage::kFaultPotStuck;
    }
}

void SensorSampler::sampleDht(kern::storage::SensorRecord& rec,
                              uint8_t& alertBits, uint8_t& faultBits)
{
    // DHT11 updates slowly, so reuse the last good reading between polls.
    if ((m_sensorTick % DHT_SAMPLE_EVERY_N_TICKS) == 0u) {
        float dhtTemp = 0.0f;
        float dhtHum = 0.0f;

        kern::sensors::Dht11::Status st = m_dht11.read(dhtTemp, dhtHum);

        if (st == kern::sensors::Dht11::Status::Ok) {
            m_lastDhtTemp = dhtTemp;
            m_lastDhtHum = dhtHum;
            m_dhtFaultBits = 0;
        } else if (st == kern::sensors::Dht11::Status::Timeout) {
            m_dhtFaultBits = kern::storage::kFaultDhtTimeout;
        } else {
            m_dhtFaultBits = kern::storage::kFaultDhtBadData;
        }
    }
    // latch the fault until the next poll so every record reports it
    faultBits |= m_dhtFaultBits;

    auto dhtTempOut = m_chDhtTemp.process(m_lastDhtTemp);
    auto dhtHumOut = m_chDhtHum.process(m_lastDhtHum);
    rec.dht_temp_c = static_cast<int16_t>(dhtTempOut.filtered * 10.0f);
    rec.dht_hum = static_cast<uint16_t>(dhtHumOut.filtered * 10.0f);
    alertBits |= alertMask(dhtTempOut.alert, kAlertDhtTempHigh, 0u);
    alertBits |= alertMask(dhtHumOut.alert, kAlertDhtHumHigh, 0u);
}

kern::storage::SensorRecord SensorSampler::sample(uint8_t state)
{
    using kern::storage::SensorRecord;

    // Assemble one telemetry record from the current sensor snapshot.
    SensorRecord rec{};
    uint8_t alertBits = 0;
    uint8_t faultBits = 0;

    uint32_t now = HAL_GetTick();
    rec.timestamp = now / 1000u;
    rec.ms = static_cast<uint16_t>(now % 1000u);
    rec.seq = ++m_recSeq;
    rec.state = state;

    sampleAnalogSensors(rec, alertBits, faultBits);
    sampleDht(rec, alertBits, faultBits);

    rec.alert_bits = alertBits;
    rec.fault_bits = faultBits;
    rec.crc32 = kern::protocol::crc32(
        reinterpret_cast<const uint8_t*>(&rec),
        offsetof(SensorRecord, crc32)
    );

    m_lastFaultBits = faultBits;
    ++m_sensorTick;
    return rec;
}

} // namespace kern::recorder
