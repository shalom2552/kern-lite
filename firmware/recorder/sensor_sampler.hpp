/*
 * SensorSampler: reads every sensor channel, runs the DSP pipeline, and
 * assembles CRC-protected SensorRecords for the Sensor task.
 *
 * file: firmware/recorder/sensor_sampler.hpp
 * author: shalom2552
 * date: 2026-07-14
 */
#pragma once

#include "stm32l4xx_hal.h"

#include "../sensors/lm35.hpp"
#include "../sensors/photodiode.hpp"
#include "../sensors/potentiometer.hpp"
#include "../sensors/dht11.hpp"
#include "../sensors/radiation_latch.hpp"
#include "../dsp/channel.hpp"
#include "../storage/sensor_record.hpp"
#include "../system/config.hpp"

#include <cstdint>

namespace kern::recorder {

/*
 * @brief Owns the sensor drivers and DSP channels; produces one filtered,
 * CRC-protected SensorRecord per sample() call.
 */
class SensorSampler {
public:
    /*
     * @brief Construct a sampler with the shared ADC handle used by the analog sensors.
     * @param adc Pointer to the ADC handle structure.
     */
    explicit SensorSampler(ADC_HandleTypeDef* adc);

    /*
     * @brief Initialize all sensor drivers once before sampling begins.
     */
    void init();

    /*
     * @brief Read, filter, and range-check every channel into one record.
     * @param state Current FSM state byte stored in the record.
     * @return Assembled SensorRecord with CRC set.
     */
    storage::SensorRecord sample(uint8_t state);

    /*
     * @brief Fault bits of the most recently assembled record.
     * @return Fault bit mask from the last sample() call.
     */
    uint8_t lastFaultBits() const { return m_lastFaultBits; }

private:
    /*
     * @brief Read, filter, and range-check the LM35, photodiode, and potentiometer channels.
     */
    void sampleAnalogSensors(storage::SensorRecord& rec, uint8_t& alertBits, uint8_t& faultBits);

    /*
     * @brief Poll the DHT11 on its slow cadence and filter the last good reading.
     */
    void sampleDht(storage::SensorRecord& rec, uint8_t& alertBits, uint8_t& faultBits);

    sensors::Lm35 m_lm35;
    sensors::Photodiode m_photo;
    sensors::Potentiometer m_pot;
    sensors::Dht11 m_dht11{};
    sensors::RadiationLatch m_latch{};

    dsp::Channel<config::kDspWindow> m_chLm35{config::kLm35Threshold};
    dsp::Channel<config::kDspWindow> m_chPhoto{config::kPhotoThreshold};
    dsp::Channel<config::kDspWindow> m_chPot{config::kPotThreshold};
    dsp::Channel<config::kDspWindow> m_chDhtTemp{config::kDhtTempThreshold};
    dsp::Channel<config::kDspWindow> m_chDhtHum{config::kDhtHumThreshold};

    uint16_t m_recSeq = 0;
    uint32_t m_sensorTick = 0;
    float m_lastDhtTemp = 0.0f;
    float m_lastDhtHum = 0.0f;
    uint8_t m_dhtFaultBits = 0;
    volatile uint8_t m_lastFaultBits = 0;
};

} // namespace kern::recorder
