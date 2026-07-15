#pragma once

#include "stm32l4xx_hal.h"

#include "../recorder/state_machine.hpp"
#include "../recorder/sensor_bus.hpp"
#include "../storage/circular_log.hpp"
#include "../recorder/comm_link.hpp"
#include "../recorder/command_handler.hpp"
#include "../recorder/sensor_sampler.hpp"
#include "../recorder/log_writer.hpp"

#include "../sensors/buttons.hpp"
#include "../storage/sensor_record.hpp"
#include "state_indicator.hpp"

/*
 * @brief Global ADC handle instance defined in main context.
 */
extern ADC_HandleTypeDef hadc1;

namespace kern::system {

/*
 * @brief Composition root wiring the recorder subsystems into the four RTOS tasks.
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
     * @brief Send one record over the comm link as a live RECORD frame.
     */
    void streamRecord(const storage::SensorRecord& rec);

    /*
     * @brief Stop the recording on a short SW1 press, flushing metadata first.
     */
    void handleShortPress();

    recorder::StateMachine m_sm;
    recorder::SensorBus m_bus;
    storage::CircularLog m_box;
    recorder::CommLink m_link;
    recorder::CommandHandler m_handler;
    sensors::Buttons m_buttons;

    recorder::SensorSampler m_sampler{&hadc1};
    recorder::LogWriter m_writer{m_sm, m_bus, m_box, m_handler};
    StateIndicator m_indicator{m_sm};
};

} // namespace kern::system
