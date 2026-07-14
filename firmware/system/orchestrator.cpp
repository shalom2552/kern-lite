#include "orchestrator.hpp"
#include "../hal/gpio.hpp"
#include "../hal/watchdog.hpp"
#include "../hal/buzzer.hpp"
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
extern TIM_HandleTypeDef htim3;

namespace kern::system {

namespace {

constexpr uint8_t MAX_WRITE_FAILS = 3;
constexpr uint32_t STATUS_HEARTBEAT_MS = 5000;
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

void Orchestrator::init()
{
    // Bring up shared subsystems before the tasks begin publishing or sending.
    m_bus.init();
    m_link.init();
    m_buttons.init();
    m_handler.bind(m_sm, m_box);

    // FR-FW-01: mount/recover storage on cold boot, before entering Idle.
    // Without this, sd_mounted stays 0 in STATUS and CMD_REPLAY NACKs
    // StorageError until the first START -- even when the card holds valid
    // data from a prior session. ensureMounted() in the Storage task still
    // owns ongoing retry/escalation to Fault (FR-FW-14) if this fails.
    m_box.mount();
}

void Orchestrator::sampleAnalogSensors(kern::storage::SensorRecord& rec,
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

void Orchestrator::sampleDht(kern::storage::SensorRecord& rec,
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
        } else if (st == kern::sensors::Dht11::Status::Timeout) {
            faultBits |= kern::storage::kFaultDhtTimeout;
        } else {
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

    // Assemble one telemetry record from the current sensor snapshot.
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

    m_lastFaultBits = faultBits;
    ++m_sensorTick;
    return rec;
}

void Orchestrator::streamRecord(const kern::storage::SensorRecord& rec)
{
    // The live stream keeps telemetry visible over UART RECORD frames.
    kern::protocol::Frame out{};
    out.type = kern::protocol::FrameType::Record;
    out.len = sizeof(kern::storage::SensorRecord);
    std::memcpy(out.payload, &rec, sizeof(kern::storage::SensorRecord));
    m_link.send(out);
}

void Orchestrator::runSensorTask()
{
    // Initialize the hardware drivers once, then publish records on a steady cadence.
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
    // In Fault, try to win the SD card back before falling back to system reset.
    if (m_box.remount() == kern::storage::StorageStatus::Ok) {
        m_faultMountFailCount = 0;
        m_writeFailPolicy.reset();
        m_sm.process(kern::recorder::Event::FaultCleared);
        // Spec 12.2: Fault -> Recording (recovery succeeded) shall send
        // STATUS immediately so the GS sees the resume without waiting up
        // to 5s for the next heartbeat.
        m_handler.sendStatus();
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
            // Spec 12.2: Recording -> Fault (3rd consecutive failure) shall
            // send STATUS immediately, not wait for the 5s heartbeat.
            m_handler.sendStatus();
        }
        return false;
    }

    m_writeFailPolicy.reset();
    return true;
}

void Orchestrator::storeLatestRecord()
{
    // Store each new record exactly once by comparing the sequence number.
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
        // Spec 12.2: same immediate-STATUS requirement as the mount-failure
        // path in ensureMounted().
        m_handler.sendStatus();
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
    // The RGB LED mirrors the FSM state; the dedicated fault LED blinks in Fault.
    if (m_sm.isFault()) {
        m_faultBlinkOn = !m_faultBlinkOn;
        if (m_faultBlinkOn) {
            hal::gpio::set(board::LED2_RED);
        } else {
            hal::gpio::clear(board::LED2_RED);
        }
        hal::gpio::set(board::RGB_R);
        hal::gpio::clear(board::RGB_G);
        hal::gpio::clear(board::RGB_B);
        return;
    }

    hal::gpio::clear(board::LED2_RED);

    if (m_sm.isLogging()) {
        if (m_lastFaultBits != 0u) {
            // Degraded-but-recording (spec 6.3): blink green instead of solid.
            m_degradedBlinkOn = !m_degradedBlinkOn;
            if (m_degradedBlinkOn) {
                hal::gpio::set(board::RGB_G);
            } else {
                hal::gpio::clear(board::RGB_G);
            }
        } else {
            m_degradedBlinkOn = false;
            hal::gpio::set(board::RGB_G);
        }
        hal::gpio::clear(board::RGB_R);
        hal::gpio::clear(board::RGB_B);
        return;
    }

    hal::gpio::clear(board::RGB_R);
    hal::gpio::clear(board::RGB_G);
    hal::gpio::clear(board::RGB_B);
}

void Orchestrator::updateStateTones(uint32_t now)
{
    kern::recorder::State state = m_sm.state();

    // A5.1 entry actions: chirp on Recording, fault tone on Fault, silence on Idle.
    if (state != m_prevState) {
        m_prevState = state;

        if (state == kern::recorder::State::Recording) {
            hal::buzzer::toneOn(htim3, kern::config::kChirpFreqHz);
            m_chirpActive = true;
            m_chirpStartMs = now;
        } else if (state == kern::recorder::State::Fault) {
            hal::buzzer::toneOn(htim3, kern::config::kFaultToneFreqHz);
            m_chirpActive = false;
        } else {
            hal::buzzer::toneOff(htim3);
            m_chirpActive = false;
        }
    }

    // The chirp is a short beep, not a continuous tone; expire it here.
    if (m_chirpActive && now - m_chirpStartMs >= kern::config::kChirpMs) {
        hal::buzzer::toneOff(htim3);
        m_chirpActive = false;
    }
}

void Orchestrator::handleShortPress()
{
    if (m_buttons.pollSw1() != kern::sensors::PressType::Short) {
        return;
    }

    if (!m_sm.isLogging()) {
        return;
    }

    // Leave Recording first so the flush does not contend with the storage
    // task for the FatFs mutex; mount recovery covers a failed flush.
    m_sm.process(kern::recorder::Event::ShortPress);
    m_box.flushMeta();
    m_handler.sendStatus();
}

void Orchestrator::runSystemTask()
{
    uint32_t lastHeartbeatMs = HAL_GetTick();

    for (;;) {
        uint32_t now = HAL_GetTick();
        hal::watchdog::kick(hiwdg);

        updateStateLeds();
        updateStateTones(now);
        handleShortPress();

        if (now - lastHeartbeatMs >= STATUS_HEARTBEAT_MS) {
            m_handler.sendStatus();
            lastHeartbeatMs = now;
        }

        vTaskDelay(pdMS_TO_TICKS(kern::config::kSystemPeriodMs));
    }
}

} // namespace kern::system
