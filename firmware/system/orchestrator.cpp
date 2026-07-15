#include "orchestrator.hpp"
#include "../hal/watchdog.hpp"
#include "config.hpp"
#include <cstring>
#include <cstdint>

#include "../protocol/frame.hpp"

#include "FreeRTOS.h"
#include "task.h"

extern IWDG_HandleTypeDef hiwdg;

namespace kern::system {

namespace {

constexpr uint32_t STATUS_HEARTBEAT_MS = 5000;

} // namespace

void Orchestrator::init()
{
    // Bring up shared subsystems before the tasks begin publishing or sending.
    m_bus.init();
    m_link.init();
    m_buttons.init();
    m_handler.bind(m_sm, m_box);

    m_box.mount();
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
    m_sampler.init();

    for (;;) {
        if (m_sm.isLogging()) {
            kern::storage::SensorRecord rec =
                m_sampler.sample(static_cast<uint8_t>(m_sm.state()));
            m_bus.publish(rec);
            streamRecord(rec);
        }

        vTaskDelay(pdMS_TO_TICKS(kern::config::kSensorPeriodMs));
    }
}

void Orchestrator::runStorageTask()
{
    for (;;) {
        m_writer.service();
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

        m_indicator.update(now, m_sampler.lastFaultBits());
        handleShortPress();

        if (now - lastHeartbeatMs >= STATUS_HEARTBEAT_MS) {
            m_handler.sendStatus();
            lastHeartbeatMs = now;
        }

        vTaskDelay(pdMS_TO_TICKS(kern::config::kSystemPeriodMs));
    }
}

} // namespace kern::system
