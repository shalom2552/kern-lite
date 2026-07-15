/*
 * LogWriter implementation: storage write policy, mount recovery, and
 * fault escalation for the Storage task.
 *
 * file: firmware/recorder/log_writer.cpp
 * author: shalom2552
 * date: 2026-07-14
 */
#include "log_writer.hpp"

#include "stm32l4xx_hal.h"

namespace kern::recorder {

void LogWriter::service()
{
    if (m_sm.isFault()) {
        recoverFromFault();
    } else if (m_sm.isLogging() && ensureMounted()) {
        storeLatestRecord();
    }
}

void LogWriter::recoverFromFault()
{
    // In Fault, try to win the SD card back before falling back to system reset.
    if (m_box.remount() == kern::storage::StorageStatus::Ok) {
        m_faultMountFailCount = 0;
        m_writeFailPolicy.reset();
        m_sm.process(Event::FaultCleared);
        m_handler.sendStatus();
        return;
    }

    if (++m_faultMountFailCount >= kern::config::kMaxWriteFails) {
        NVIC_SystemReset();
    }
}

bool LogWriter::ensureMounted()
{
    if (m_box.isMounted()) {
        return true;
    }

    if (m_box.mount() != kern::storage::StorageStatus::Ok) {
        if (m_writeFailPolicy.recordFailure()) {
            m_sm.process(Event::SdFault);
            m_handler.sendStatus();
        }
        return false;
    }

    m_writeFailPolicy.reset();
    return true;
}

void LogWriter::storeLatestRecord()
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
        m_sm.process(Event::SdFault);
        m_handler.sendStatus();
    }
}

} // namespace kern::recorder
