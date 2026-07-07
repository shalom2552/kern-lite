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
#include "../dsp/channel.hpp"
#include "../storage/sensor_record.hpp"
#include "config.hpp"

#include <cstdint>

extern ADC_HandleTypeDef hadc1;

namespace kern::system {

class Orchestrator {
public:
    void init();
    void runSensorTask();
    void runStorageTask();
    void runCommsTask();
    void runSystemTask();
    static Orchestrator& instance() { static Orchestrator o; return o; }
private:
    storage::SensorRecord assembleRecord();

    recorder::StateMachine m_sm;
    recorder::SensorBus m_bus;
    storage::CircularLog m_box;
    recorder::CommLink m_link;
    recorder::CommandHandler m_handler;

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
    float m_lastDhtTemp = 0.0f;
    float m_lastDhtHum = 0.0f;
};

}
