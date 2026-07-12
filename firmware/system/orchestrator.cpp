#include "orchestrator.hpp"
#include "../hal/gpio.hpp"
#include "../hal/watchdog.hpp"
#include "board.hpp"
#include "config.hpp"
#include <cstring>
#include <cstdint>
#include <cstddef>

#include "../sensors/dht11.hpp"
#include "../dsp/threshold_detector.hpp"
#include "../protocol/frame.hpp"
#include "../protocol/crc32.hpp"

#include "FreeRTOS.h"
#include "task.h"



extern ADC_HandleTypeDef hadc1;
extern UART_HandleTypeDef huart2;
extern IWDG_HandleTypeDef hiwdg;

namespace kern::system {

namespace {

constexpr uint8_t MAX_WRITE_FAILS = 3;
constexpr uint32_t STATUS_HEARTBEAT_MS = 5000;
constexpr uint32_t DHT_SAMPLE_EVERY_N_TICKS = 20;

/*
 * Alert bits are packed exactly like the host decoder expects, channel by
 * channel, so downstream tooling can reuse the same bitmask semantics.
 */
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

} /* namespace */

void Orchestrator::init()
{
    /*
     * Bring up shared subsystems before the tasks begin publishing or sending.
     */
    m_bus.init();
    m_link.init();
    m_buttons.init();
    m_handler.bind(m_sm, m_box);
}

void Orchestrator::sampleAnalogSensors(kern::storage::SensorRecord& rec,
                                       uint8_t& alertBits, uint8_t& faultBits)
{
    /*
     * Range checks map directly to the fault bit layout used by telemetry.py so
     * the host and firmware agree on the meaning of each fault bit.
     */
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

void Orchestrator::sampleDht(kern::storage::SensorRecord& rec,
                             uint8_t& alertBits, uint8_t& faultBits)
{
    /*
     * DHT11 updates slowly, so sample it on a lower cadence and reuse the last
     * good reading between polls instead of stalling the whole record loop.
     */
    if ((m_sensorTick % DHT_SAMPLE_EVERY_N_TICKS) == 0u) {
        float dhtTemp = 0.0f;
        float dhtHum = 0.0f;

        kern::sensors::Dht11::Status st = m_dht11.read(dhtTemp, dhtHum);

        if (st == kern::sensors::Dht11::Status::Ok) {
            m_lastDhtTemp = dhtTemp;
            m_lastDhtHum = dhtHum;
        }
        else if (st == kern::sensors::Dht11::Status::Timeout) {
            faultBits |= kern::storage::kFaultDhtTimeout;
        }
        else {
            faultBits |= kern::storage::kFaultDhtBadData;
        }
    }

    auto dhtTempOut = m_chDhtTemp.process(m_lastDhtTemp);
    auto dhtHumOut = m_chDhtHum.process(m_lastDhtHum);
    rec.dht_temp_c = static_cast<int16_t>(dhtTempOut.filtered * 10.0f);
    rec.dht_hum = static_cast<uint16_t>(dhtHumOut.filtered * 10.0f);
    alertBits |= alertMask(dhtTempOut.alert, kAlertDhtTempHigh, 0u);
    alertBits |= alertMask(dhtHumOut.alert, kAlertDhtHumHigh, 0u);
}

kern::storage::SensorRecord Orchestrator::assembleRecord()
{
    using kern::storage::SensorRecord;

    /*
     * Assemble one telemetry record from the current sensor snapshot, then
     * translate raw sensor values into the packed record layout used on disk
     * and on the wire.
     */
    SensorRecord rec{};
    uint8_t alertBits = 0;
    uint8_t faultBits = 0;

    uint32_t now = HAL_GetTick();
    rec.timestamp = now / 1000u;
    rec.ms = static_cast<uint16_t>(now % 1000u);
    rec.seq = ++m_recSeq;
    rec.state = static_cast<uint8_t>(m_sm.state());

    sampleAnalogSensors(rec, alertBits, faultBits);
    sampleDht(rec, alertBits, faultBits);

    rec.alert_bits = alertBits;
    rec.fault_bits = faultBits;
    rec.crc32 = kern::protocol::crc32(
        reinterpret_cast<const uint8_t*>(&rec),
        offsetof(SensorRecord, crc32)
    );

    ++m_sensorTick;
    return rec;
}

void Orchestrator::streamRecord(const kern::storage::SensorRecord& rec)
{
    /*
     * The live stream keeps telemetry visible while the comms pipeline is
     * still in transition to a dedicated RECORD framing path.
     */
    kern::protocol::Frame out{};
    out.type = kern::protocol::FrameType::Record;
    out.len = sizeof(kern::storage::SensorRecord);
    std::memcpy(out.payload, &rec, sizeof(kern::storage::SensorRecord));
    m_link.send(out);
}

void Orchestrator::runSensorTask()
{
    /*
     * Initialize the hardware drivers once, then keep publishing records on a
     * steady cadence so the storage and comms tasks can consume them.
     */
    m_lm35.init();
    m_dht11.init();
    m_latch.init();
    m_photo.init();
    m_pot.init();

    for (;;) {
        if (m_sm.isLogging()) {
            kern::storage::SensorRecord rec = assembleRecord();
            m_bus.publish(rec);
            streamRecord(rec);
        }

        vTaskDelay(pdMS_TO_TICKS(kern::config::kSensorPeriodMs));
    }
}

void Orchestrator::recoverFromFault()
{
    /*
     * In Fault the only job is to win the SD card back; after too many failed
     * remounts fall back to a full system reset per the Day 5 fault policy.
     */
    if (m_box.remount() == kern::storage::StorageStatus::Ok) {
        m_faultMountFailCount = 0;
        m_writeFailPolicy.reset();
        m_sm.process(kern::recorder::Event::FaultCleared);
        return;
    }

    if (++m_faultMountFailCount >= MAX_WRITE_FAILS) {
        NVIC_SystemReset();
    }
}

bool Orchestrator::ensureMounted()
{
    if (m_box.isMounted()) {
        return true;
    }

    if (m_box.mount() != kern::storage::StorageStatus::Ok) {
        if (m_writeFailPolicy.recordFailure()) {
            m_sm.process(kern::recorder::Event::SdFault);
        }
        return false;
    }

    m_writeFailPolicy.reset();
    return true;
}

void Orchestrator::storeLatestRecord()
{
    /*
     * Store each new record exactly once by comparing the sequence number
     * against the last committed value.
     */
    kern::storage::SensorRecord rec = m_bus.latest();
    if (rec.seq == m_lastStoredSeq) {
        return;
    }

    kern::storage::StorageStatus st = m_box.writeRecord(rec);
    if (st == kern::storage::StorageStatus::Ok) {
        m_lastStoredSeq = rec.seq;
        m_writeFailPolicy.reset();
    } else if (m_writeFailPolicy.recordFailure()) {
        m_sm.process(kern::recorder::Event::SdFault);
    }
}

void Orchestrator::runStorageTask()
{
    for (;;) {
        if (m_sm.isFault()) {
            recoverFromFault();
        } else if (m_sm.isLogging() && ensureMounted()) {
            storeLatestRecord();
        }

        vTaskDelay(pdMS_TO_TICKS(kern::config::kStoragePeriodMs));
    }
}

void Orchestrator::runCommsTask()
{
    for (;;) {
        kern::protocol::Frame f{};
        if (m_link.poll(f)) {
            m_handler.dispatch(f);
        }
        vTaskDelay(pdMS_TO_TICKS(kern::config::kCommsPeriodMs));
    }
}

void Orchestrator::updateStateLeds()
{
    /*
     * The RGB LED mirrors the FSM: solid green while recording, blinking red
     * in fault, everything off in idle.
     */
    if (m_sm.isLogging()) {
        hal::gpio::set(board::RGB_G);
        hal::gpio::clear(board::RGB_R);
        hal::gpio::clear(board::RGB_B);
        return;
    }

    if (m_sm.isFault()) {
        m_faultBlinkOn = !m_faultBlinkOn;
        if (m_faultBlinkOn) {
            hal::gpio::set(board::RGB_R);
        } else {
            hal::gpio::clear(board::RGB_R);
        }
        hal::gpio::clear(board::RGB_G);
        hal::gpio::clear(board::RGB_B);
        return;
    }

    hal::gpio::clear(board::RGB_R);
    hal::gpio::clear(board::RGB_G);
    hal::gpio::clear(board::RGB_B);
}

void Orchestrator::handleShortPress()
{
    if (m_buttons.pollSw1() != kern::sensors::PressType::Short) {
        return;
    }

    if (!m_sm.isLogging()) {
        return;
    }

    /*
     * A short press stops the recording; flush metadata first so the ring
     * position survives the transition back to Idle.
     */
    if (m_box.flushMeta() != kern::storage::StorageStatus::Ok) {
        m_handler.sendNack(kern::protocol::NackCode::StorageError);
        m_handler.sendStatus();
        return;
    }

    m_sm.process(kern::recorder::Event::ShortPress);
    m_handler.sendStatus();
}

void Orchestrator::runSystemTask()
{
    uint32_t lastHeartbeatMs = HAL_GetTick();

    for (;;) {
        uint32_t now = HAL_GetTick();
        hal::watchdog::kick(hiwdg);

        updateStateLeds();
        handleShortPress();

        if (now - lastHeartbeatMs >= STATUS_HEARTBEAT_MS) {
            m_handler.sendStatus();
            lastHeartbeatMs = now;
        }

        vTaskDelay(pdMS_TO_TICKS(kern::config::kSystemPeriodMs));
    }
}

} /* namespace kern::system */
