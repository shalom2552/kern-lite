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

namespace {
constexpr uint8_t MAX_WRITE_FAILS = 3;
constexpr uint32_t STATUS_HEARTBEAT_MS = 5000;
}

void Orchestrator::init()
{
	// Bring up shared subsystems before the tasks begin publishing or sending.
    m_bus.init();
    m_link.init();
    m_buttons.init();
    m_handler.bind(m_sm, m_box);
}

kern::storage::SensorRecord Orchestrator::assembleRecord()
{
	using kern::dsp::ThresholdDetector;
	using kern::storage::SensorRecord;

	// Assemble one telemetry record from the current sensor snapshot, then
	// translate raw sensor values into the packed record layout used on disk
	// and on the wire.
	SensorRecord rec{};
	uint8_t alertBits = 0;
	uint8_t faultBits = 0;

	uint32_t now = HAL_GetTick();
	rec.timestamp = now / 1000u;
	rec.ms = static_cast<uint16_t>(now % 1000u);
	rec.seq = ++m_recSeq;
	rec.state = static_cast<uint8_t>(m_sm.state());

	float lm35Temp = m_lm35.readCelsius();
	auto lm35Out = m_chLm35.process(lm35Temp);
	rec.lm35_c = static_cast<int16_t>(lm35Out.filtered * 10.0f);
	// Range checks map directly to the fault bit layout used by telemetry.py so
	// the host and firmware agree on the meaning of each fault bit.
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

	// DHT11 updates slowly, so sample it on a lower cadence and reuse the last
	// good reading between polls instead of stalling the whole record loop.
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

	// Alert bits are packed exactly like the host decoder expects, channel by
	// channel, so downstream tooling can reuse the same bitmask semantics.
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
	// Initialize the hardware drivers once, then keep publishing records on a
	// steady cadence so the storage and comms tasks can consume them.
	m_lm35.init();
	m_dht11.init();
	m_latch.init();
	m_photo.init();
	m_pot.init();

	for (;;) {
		if (!m_sm.isLogging()) {
			vTaskDelay(pdMS_TO_TICKS(kern::config::kSensorPeriodMs));
			continue;
		}

		kern::storage::SensorRecord rec = assembleRecord();
		m_bus.publish(rec);

		// The live stream keeps telemetry visible while the comms pipeline is
		// still in transition to a dedicated RECORD framing path.
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
        if (m_sm.isFault()) {
            if (m_box.isMounted() || m_box.mount() == kern::storage::StorageStatus::Ok) {
                m_faultMountFailCount = 0;
                m_writeFailCount = 0;
                m_sm.process(kern::recorder::Event::FaultCleared);
            } else if (++m_faultMountFailCount >= MAX_WRITE_FAILS) {
                NVIC_SystemReset();
            }

            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        if (!m_sm.isLogging()) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        if (!m_box.isMounted()) {
            if (m_box.mount() != kern::storage::StorageStatus::Ok) {
                if (++m_writeFailCount >= MAX_WRITE_FAILS) {
                    m_sm.process(kern::recorder::Event::SdFault);
                }
                vTaskDelay(pdMS_TO_TICKS(100));
                continue;
            }
            m_writeFailCount = 0;
        }

	    // Store each new record exactly once by comparing the sequence number
	    // against the last committed value.
        kern::storage::SensorRecord rec = m_bus.latest();
        if (rec.seq != m_lastStoredSeq) {
            kern::storage::StorageStatus st = m_box.writeRecord(rec);
            if (st == kern::storage::StorageStatus::Ok) {
                m_lastStoredSeq = rec.seq;
                m_writeFailCount = 0;
            } else if (++m_writeFailCount >= MAX_WRITE_FAILS) {
                m_sm.process(kern::recorder::Event::SdFault);
            }
        }

        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

void Orchestrator::runCommsTask()
{
    for (;;) {
        kern::protocol::Frame f{};
        if (m_link.poll(f)) {
            m_handler.dispatch(f);
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void Orchestrator::runSystemTask()
{
    uint32_t lastHeartbeatMs = HAL_GetTick();
    bool faultBlinkOn = false;

    for (;;) {
        uint32_t now = HAL_GetTick();
        hal::watchdog::kick(hiwdg);

        if (m_sm.isLogging()) {
            hal::gpio::set(board::RGB_G);
            hal::gpio::clear(board::RGB_R);
            hal::gpio::clear(board::RGB_B);
        } else if (m_sm.isFault()) {
            faultBlinkOn = !faultBlinkOn;
            if (faultBlinkOn) {
                hal::gpio::set(board::RGB_R);
            } else {
                hal::gpio::clear(board::RGB_R);
            }
            hal::gpio::clear(board::RGB_G);
            hal::gpio::clear(board::RGB_B);
        } else {
            hal::gpio::clear(board::RGB_R);
            hal::gpio::clear(board::RGB_G);
            hal::gpio::clear(board::RGB_B);
        }

        if (m_buttons.pollSw1() == kern::sensors::PressType::Short) {
            if (m_sm.process(kern::recorder::Event::ShortPress)) {
                m_box.flushMeta();
                m_handler.sendStatus();
            }
        }

        if (now - lastHeartbeatMs >= STATUS_HEARTBEAT_MS) {
            m_handler.sendStatus();
            lastHeartbeatMs = now;
        }

        vTaskDelay(pdMS_TO_TICKS(kern::config::kSystemPeriodMs));
    }
}

}
