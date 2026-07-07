#include "orchestrator.hpp"
#include "../hal/gpio.hpp"
#include "../hal/watchdog.hpp"
#include "board.hpp"
#include "config.hpp"
#include <cstring>
#include <cstdint>

#include "../sensors/lm35.hpp"
#include "../sensors/dht11.hpp"
#include "../sensors/radiation_latch.hpp"
#include "../sensors/photodiode.hpp"
#include "../sensors/potentiometer.hpp"

#include "../dsp/channel.hpp"
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
    bus.init();
    link.init();
}

void Orchestrator::runSensorTask()
{
	//getting all the verbs ready
	using kern::dsp::ThresholdDetector;
	using kern::storage::SensorRecord;

	static kern::sensors::Dht11 dht11_s;
	static kern::sensors::RadiationLatch latch_s;
	static kern::sensors::Lm35 lm35_s(&hadc1);
	static kern::sensors::Photodiode photo_s(&hadc1);
	static kern::sensors::Potentiometer pot_s(&hadc1);

	// getting there thresholds
	static kern::dsp::Channel<kern::config::kDspWindow> chLm35(kern::config::kLm35Threshold);
	static kern::dsp::Channel<kern::config::kDspWindow> chPhoto(kern::config::kPhotoThreshold);
	static kern::dsp::Channel<kern::config::kDspWindow> chPot(kern::config::kPotThreshold);
	static kern::dsp::Channel<kern::config::kDspWindow> chDhtTemp(kern::config::kDhtTempThreshold);
	static kern::dsp::Channel<kern::config::kDspWindow> chDhtHum(kern::config::kDhtHumThreshold);

	static bool initialized = false;
	static uint16_t recSeq = 0;
	static uint32_t sensorTick = 0;

	static float lastDhtTemp = 0.0f;
	static float lastDhtHum = 0.0f;

	if (!initialized) {
		lm35_s.init();
		dht11_s.init();
		latch_s.init();
		photo_s.init();
		pot_s.init();

		initialized = true;
	}

	for (;;) {
		SensorRecord rec{};
		uint8_t alertBits = 0;
		uint8_t faultBits = 0;

		uint32_t now = HAL_GetTick();

		rec.timestamp = now / 1000u;
		rec.ms = static_cast<uint16_t>(now % 1000u);
		rec.seq = ++recSeq;
		rec.state = 0; //Later connect to state machine.

		//read sensors
		float lm35Temp = lm35_s.readCelsius();
		auto lm35Out = chLm35.process(lm35Temp);
		rec.lm35_c = static_cast<int16_t>(lm35Out.filtered * 10.0f);

		//if range is wrong
		if (lm35Temp < -10.0f || lm35Temp > 100.0f) {
			faultBits |= kern::storage::kFaultLm35Range;
		}

		float lightRaw = photo_s.readNormalized();
		auto photoOut = chPhoto.process(lightRaw);
		rec.light = static_cast<uint16_t>(photoOut.filtered * 65535.0f);

		if (lightRaw <= 0.001f || lightRaw >= 0.999f) {
			faultBits |= kern::storage::kFaultLightStuck;
		}

		float potRaw = pot_s.readNormalized();
		auto potOut = chPot.process(potRaw);
		rec.pot = static_cast<uint16_t>(potOut.filtered * 65535.0f);

		if (potRaw <= 0.001f || potRaw >= 0.999f) {
			faultBits |= kern::storage::kFaultPotStuck;
		}

		//read DHT11 every 20 ticks
		if ((sensorTick % 20u) == 0u) {
			float dhtTemp = 0.0f;
			float dhtHum = 0.0f;

			kern::sensors::Dht11::Status st = dht11_s.read(dhtTemp, dhtHum);

			if (st == kern::sensors::Dht11::Status::Ok) {
				lastDhtTemp = dhtTemp;
				lastDhtHum = dhtHum;
			}
			else if (st == kern::sensors::Dht11::Status::Timeout) {
				faultBits |= kern::storage::kFaultDhtTimeout;
			}
			else {
				faultBits |= kern::storage::kFaultDhtBadData;
			}
		}

		//read temp and hume
		auto dhtTempOut = chDhtTemp.process(lastDhtTemp);
		auto dhtHumOut = chDhtHum.process(lastDhtHum);

		//cast them to int from float
		rec.dht_temp_c = static_cast<int16_t>(dhtTempOut.filtered * 10.0f);
		rec.dht_hum = static_cast<uint16_t>(dhtHumOut.filtered * 10.0f);

		if (latch_s.consumeEvent()) {
			//no action today. Event system removed for Day 3.
		}

		// alert_bits mapping must match spec 9.4 and groundstation/telemetry.py
		// lm35: high=0x01, low=0x02
		if (lm35Out.alert == ThresholdDetector::State::HighAlert) {
			alertBits |= 0x01;
		}
		else if (lm35Out.alert == ThresholdDetector::State::LowAlert) {
			alertBits |= 0x02;
		}

		// light: high=0x04, low=0x08
		if (photoOut.alert == ThresholdDetector::State::HighAlert) {
			alertBits |= 0x04;
		}
		else if (photoOut.alert == ThresholdDetector::State::LowAlert) {
			alertBits |= 0x08;
		}

		// pot: high=0x10, low=0x20
		if (potOut.alert == ThresholdDetector::State::HighAlert) {
			alertBits |= 0x10;
		}
		else if (potOut.alert == ThresholdDetector::State::LowAlert) {
			alertBits |= 0x20;
		}

		// dht_temp: only high alert exists = 0x40
		if (dhtTempOut.alert == ThresholdDetector::State::HighAlert) {
			alertBits |= 0x40;
		}

		// dht_hum: only high alert exists = 0x80
		if (dhtHumOut.alert == ThresholdDetector::State::HighAlert) {
			alertBits |= 0x80;
		}

		// update in the record its fields
		rec.alert_bits = alertBits;
		rec.fault_bits = faultBits;
		// make crc code and update it
		rec.crc32 = kern::protocol::crc32(
			reinterpret_cast<const uint8_t*>(&rec),
			offsetof(SensorRecord, crc32)
		);
		//send it via bus so others can use what we recorded .
		bus.publish(rec);


		kern::protocol::Frame out{};
		out.type = kern::protocol::FrameType::Record;
		out.len = sizeof(SensorRecord);
		// coppy our record to a frame
		std::memcpy(out.payload, &rec, sizeof(SensorRecord));
		// send it via uart
		link.send(out);

		++sensorTick;

		vTaskDelay(pdMS_TO_TICKS(kern::config::kSensorPeriodMs));
	}
}

void Orchestrator::runStorageTask()
{
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

void Orchestrator::runCommsTask()
{
    for (;;) {
        kern::protocol::Frame f{};
        if (link.poll(f)) {
            handler.dispatch(f); // stub handler
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void Orchestrator::runSystemTask()
{

    static const char msg[] = "KERN-LITE ALIVE\r\n";
    for (;;) {
        hal::gpio::toggle(board::LED1_BLUE);
        HAL_UART_Transmit(&huart2, reinterpret_cast<const uint8_t*>(msg), sizeof(msg)-1, 100);
        hal::watchdog::kick(hiwdg);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

}
