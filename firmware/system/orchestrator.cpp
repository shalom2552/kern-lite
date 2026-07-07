#include "orchestrator.hpp"
#include "../hal/gpio.hpp"
#include "../hal/watchdog.hpp"
#include "board.hpp"
#include "config.hpp"
#include <cstring>
#include <cstdint>

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

void Orchestrator::init()
{
    m_bus.init();
    m_link.init();
}

kern::storage::SensorRecord Orchestrator::assembleRecord()
{
	using kern::dsp::ThresholdDetector;
	using kern::storage::SensorRecord;

	SensorRecord rec{};
	uint8_t alertBits = 0;
	uint8_t faultBits = 0;

	uint32_t now = HAL_GetTick();
	rec.timestamp = now / 1000u;
	rec.ms = static_cast<uint16_t>(now % 1000u);
	rec.seq = ++m_recSeq;
	rec.state = 0;

	float lm35Temp = m_lm35.readCelsius();
	auto lm35Out = m_chLm35.process(lm35Temp);
	rec.lm35_c = static_cast<int16_t>(lm35Out.filtered * 10.0f);
	if (lm35Temp < -10.0f || lm35Temp > 100.0f) {
		faultBits |= kern::storage::kFaultLm35Range;
	}

	float lightRaw = m_photo.readNormalized();
	auto photoOut = m_chPhoto.process(lightRaw);
	rec.light = static_cast<uint16_t>(photoOut.filtered * 65535.0f);
	if (lightRaw <= 0.001f || lightRaw >= 0.999f) {
		faultBits |= kern::storage::kFaultLightStuck;
	}

	float potRaw = m_pot.readNormalized();
	auto potOut = m_chPot.process(potRaw);
	rec.pot = static_cast<uint16_t>(potOut.filtered * 65535.0f);
	if (potRaw <= 0.001f || potRaw >= 0.999f) {
		faultBits |= kern::storage::kFaultPotStuck;
	}

	// DHT11 supports ~2 s updates; sample every 20 ticks and reuse the last good value.
	if ((m_sensorTick % 20u) == 0u) {
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

	// alert_bits per spec 9.4; must match groundstation/telemetry.py.
	if (lm35Out.alert == ThresholdDetector::State::HighAlert) {
		alertBits |= 0x01;
	}
	else if (lm35Out.alert == ThresholdDetector::State::LowAlert) {
		alertBits |= 0x02;
	}

	if (photoOut.alert == ThresholdDetector::State::HighAlert) {
		alertBits |= 0x04;
	}
	else if (photoOut.alert == ThresholdDetector::State::LowAlert) {
		alertBits |= 0x08;
	}

	if (potOut.alert == ThresholdDetector::State::HighAlert) {
		alertBits |= 0x10;
	}
	else if (potOut.alert == ThresholdDetector::State::LowAlert) {
		alertBits |= 0x20;
	}

	if (dhtTempOut.alert == ThresholdDetector::State::HighAlert) {
		alertBits |= 0x40;
	}

	if (dhtHumOut.alert == ThresholdDetector::State::HighAlert) {
		alertBits |= 0x80;
	}

	rec.alert_bits = alertBits;
	rec.fault_bits = faultBits;
	rec.crc32 = kern::protocol::crc32(
		reinterpret_cast<const uint8_t*>(&rec),
		offsetof(SensorRecord, crc32)
	);

	++m_sensorTick;
	return rec;
}

void Orchestrator::runSensorTask()
{
	m_lm35.init();
	m_dht11.init();
	m_latch.init();
	m_photo.init();
	m_pot.init();

	for (;;) {
		kern::storage::SensorRecord rec = assembleRecord();
		m_bus.publish(rec);

		// Temporary live stream until the Comms task owns RECORD framing in Phase 5.
		kern::protocol::Frame out{};
		out.type = kern::protocol::FrameType::Record;
		out.len = sizeof(kern::storage::SensorRecord);
		std::memcpy(out.payload, &rec, sizeof(kern::storage::SensorRecord));
		m_link.send(out);

		vTaskDelay(pdMS_TO_TICKS(kern::config::kSensorPeriodMs));
	}
}

void Orchestrator::runStorageTask()
{
    for (;;) {
        if (!m_box.isMounted()) {
            m_box.mount();
        }
        else {
            // Write each record the Sensor task posts exactly once. State guards
            // come in Phase 5; for now, write whenever mounted.
            kern::storage::SensorRecord rec = m_bus.latest();
            if (rec.seq != m_lastStoredSeq) {
                m_box.writeRecord(rec);
                m_lastStoredSeq = rec.seq;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(kern::config::kSensorPeriodMs / 2));
    }
}

void Orchestrator::runCommsTask()
{
    for (;;) {
        kern::protocol::Frame f{};
        if (m_link.poll(f)) {
            m_handler.dispatch(f); // stub handler
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void Orchestrator::runSystemTask()
{
    // PC9 is the only liveness indicator until state-based LEDs are wired in Day 5,
    // so blink it at 1 Hz from the 50 ms System task.
    const uint32_t ledTicks = 1000u / kern::config::kSystemPeriodMs;
    uint32_t ledCounter = 0;

    for (;;) {
        hal::watchdog::kick(hiwdg);

        if (++ledCounter >= ledTicks) {
            hal::gpio::toggle(board::LED1_BLUE);
            ledCounter = 0;
        }

        vTaskDelay(pdMS_TO_TICKS(kern::config::kSystemPeriodMs));
    }
}

}
