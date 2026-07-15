/*
 * LogWriter: storage-side policy for the Storage task - mount management,
 * exactly-once record persistence, and fault recovery with reset escalation.
 *
 * file: firmware/recorder/log_writer.hpp
 * author: shalom2552
 * date: 2026-07-14
 */
#pragma once

#include "state_machine.hpp"
#include "sensor_bus.hpp"
#include "command_handler.hpp"
#include "../storage/circular_log.hpp"
#include "../system/config.hpp"
#include "../system/write_failure_policy.hpp"

#include <cstdint>

namespace kern::recorder {

/*
 * @brief Drives the storage side of the recorder: writes the latest published
 * record while Recording and wins the SD card back while in Fault.
 */
class LogWriter {
public:
    /*
     * @brief Construct a writer bound to the shared recorder subsystems.
     */
    LogWriter(StateMachine& sm, SensorBus& bus, storage::CircularLog& box,
              CommandHandler& handler)
        : m_sm(sm)
        , m_bus(bus)
        , m_box(box)
        , m_handler(handler)
    {
    }

    /*
     * @brief One Storage task iteration: recover in Fault, otherwise persist
     * the newest record while Recording.
     */
    void service();

private:
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

    StateMachine& m_sm;
    SensorBus& m_bus;
    storage::CircularLog& m_box;
    CommandHandler& m_handler;

    system::WriteFailurePolicy m_writeFailPolicy{config::kMaxWriteFails};
    uint8_t m_faultMountFailCount = 0;
    uint16_t m_lastStoredSeq = 0;
};

} // namespace kern::recorder
