#pragma once

#include "stm32l4xx_hal.h"

#include "../recorder/state_machine.hpp"
#include "../recorder/sensor_bus.hpp"
#include "../storage/circular_log.hpp"
#include "../recorder/comm_link.hpp"
#include "../recorder/command_handler.hpp"

#include "../sensors/lm35.hpp"
#include "../sensors/photodiode.hpp"
#include "../sensors/potentiometer.hpp"
#include "../sensors/dht11.hpp"
#include "../sensors/radiation_latch.hpp"
#include "../sensors/buttons.hpp"
#include "../dsp/channel.hpp"
#include "../storage/sensor_record.hpp"
#include "config.hpp"
#include "write_failure_policy.hpp"

#include <cstdint>

/*
 * @brief Global ADC handle instance defined in main context.
 */
extern ADC_HandleTypeDef hadc1;

namespace kern::system {

/*
 * @brief Main system orchestrator coordinating tasks, sensor polling, logging, and communications.
 */
class Orchestrator {
public:
    /*
     * @brief Initialize all sub-modules (sensors, storage, comm link).
     */
    void init();

    /*
     * @brief Periodic task execution function for sensor polling and filtering.
     */
    void runSensorTask();

    /*
     * @brief Periodic task execution function for flushing records to storage.
     */
    void runStorageTask();

    /*
     * @brief Periodic task execution function for handling protocol communication.
     */
    void runCommsTask();

    /*
     * @brief Periodic task execution function for system health monitoring and state transitions.
     */
    void runSystemTask();

    /*
     * @brief Get the singleton instance of the Orchestrator.
     * @return Reference to the Orchestrator instance.
     */
    static Orchestrator& instance()
    {
        static Orchestrator o;
        return o;
    }

private:
    /*
     * @brief Collect filtered sensor values and package them into a SensorRecord.
     * @return Generated SensorRecord.
     */
    storage::SensorRecord assembleRecord();

    /*
     * @brief Read, filter, and range-check the LM35, photodiode, and potentiometer channels.
     */
    void sampleAnalogSensors(storage::SensorRecord& rec, uint8_t& alertBits, uint8_t& faultBits);

    /*
     * @brief Poll the DHT11 on its slow cadence and filter the last good reading.
     */
    void sampleDht(storage::SensorRecord& rec, uint8_t& alertBits, uint8_t& faultBits);

    /*
     * @brief Send one record over the comm link as a live RECORD frame.
     */
    void streamRecord(const storage::SensorRecord& rec);

    /*
     * @brief Attempt an SD remount while in Fault; reset the board after repeated failures.
     */
    void recoverFromFault();

    /*
     * @brief Mount the SD card if needed, escalating to SdFault on repeated failures.
     * @return true when the card is mounted and writable.
     */
    bool ensureMounted();

    /*
     * @brief Write the newest published record to storage exactly once.
     */
    void storeLatestRecord();

    /*
     * @brief Drive the RGB LED pattern for the current FSM state.
     */
    void updateStateLeds();

    /*
     * @brief Stop the recording on a short SW1 press, flushing metadata first.
     */
    void handleShortPress();

    /*
     * @brief Fire the buzzer entry actions on state transitions and expire the chirp.
     */
    void updateStateTones(uint32_t now);

    recorder::StateMachine m_sm;
    recorder::SensorBus m_bus;
    storage::CircularLog m_box;
    recorder::CommLink m_link;
    recorder::CommandHandler m_handler;
    sensors::Buttons m_buttons;

    sensors::Lm35 m_lm35{&hadc1};
    sensors::Photodiode m_photo{&hadc1};
    sensors::Potentiometer m_pot{&hadc1};
    sensors::Dht11 m_dht11{};
    sensors::RadiationLatch m_latch{};

    dsp::Channel<config::kDspWindow> m_chLm35{config::kLm35Threshold};
    dsp::Channel<config::kDspWindow> m_chPhoto{config::kPhotoThreshold};
    dsp::Channel<config::kDspWindow> m_chPot{config::kPotThreshold};
    dsp::Channel<config::kDspWindow> m_chDhtTemp{config::kDhtTempThreshold};
    dsp::Channel<config::kDspWindow> m_chDhtHum{config::kDhtHumThreshold};

    uint16_t m_recSeq = 0;
    uint16_t m_lastStoredSeq = 0;
    uint32_t m_sensorTick = 0;
    WriteFailurePolicy m_writeFailPolicy{};
    uint8_t m_faultMountFailCount = 0;
    bool m_faultBlinkOn = false;
    recorder::State m_prevState = recorder::State::Idle;
    bool m_chirpActive = false;
    uint32_t m_chirpStartMs = 0;
    float m_lastDhtTemp = 0.0f;
    float m_lastDhtHum = 0.0f;
};

} // namespace kern::system
