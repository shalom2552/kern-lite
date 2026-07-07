/*
DHT11 temperature and humidity sensor driver implementation.

file: firmware/sensors/dht11.cpp
author: Smallejoo
date: 2026-06-07
*/

#include "dht11.hpp"

namespace kern::sensors {

namespace {

uint16_t dhtPinMask()
{
	//board::DHT_DATA.n is pin number, HAL needs pin mask
	return static_cast<uint16_t>(1u << kern::board::DHT_DATA.n);
}

}

void Dht11::init()
{
	// enable DWT counter for microsecond delay
	CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
	DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
	DWT->CYCCNT = 0;

	pinInput();
}

Dht11::Status Dht11::read(float& tempC, float& humidity)
{
	tempC = 0.0f;
	humidity = 0.0f;

	uint32_t startMs = HAL_GetTick();

	uint8_t data[5]{};

	// start signal, but keep it short because task says max 5ms block
	// if there is a problem then we should wait longer . need to test this .
	pinOutput();
	writePin(GPIO_PIN_RESET);
	delayUs(1000); // 1ms low, not 18ms, because handbook says max 5ms
					// if we fail to read then maybe we need to wait more time .

	writePin(GPIO_PIN_SET);
	delayUs(30);

	pinInput();

	if (timedOut(startMs)) {
		return Status::Timeout;
	}

	//DHT response: LOW -> HIGH -> LOW
	if (!waitForLevel(GPIO_PIN_RESET, startMs)) {
		return Status::Timeout;
	}

	if (!waitForLevel(GPIO_PIN_SET, startMs)) {
		return Status::Timeout;
	}

	if (!waitForLevel(GPIO_PIN_RESET, startMs)) {
		return Status::Timeout;
	}

	// read 40 bits
	for (int bit = 0; bit < 40; ++bit) {
		if (!waitForLevel(GPIO_PIN_SET, startMs)) {
			return Status::Timeout;
		}

		//after 40us, if pin is still HIGH, it is probably bit 1
		delayUs(40);

		bool isOne = (readPin() == GPIO_PIN_SET);

		if (!waitForLevel(GPIO_PIN_RESET, startMs)) {
			return Status::Timeout;
		}

		data[bit / 8] <<= 1;

		if (isOne) {
			data[bit / 8] |= 1u;
		}

		if (timedOut(startMs)) {
			return Status::Timeout;
		}
	}

	//DHT11 checksum
	uint8_t crc = static_cast<uint8_t>(
		data[0] + data[1] + data[2] + data[3]
	);

	if (crc != data[4]) {
		return Status::CrcError;
	}

	//DHT11 integer format
	humidity = static_cast<float>(data[0]);
	tempC = static_cast<float>(data[2]);

	return Status::Ok;
}

void Dht11::pinOutput()
{
	GPIO_InitTypeDef GPIO_InitStruct{};

	GPIO_InitStruct.Pin = dhtPinMask();
	GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_OD;
	GPIO_InitStruct.Pull = GPIO_NOPULL;
	GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;

	HAL_GPIO_Init(kern::board::DHT_DATA.port, &GPIO_InitStruct);
}

void Dht11::pinInput()
{
	GPIO_InitTypeDef GPIO_InitStruct{};

	GPIO_InitStruct.Pin = dhtPinMask();
	GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
	GPIO_InitStruct.Pull = GPIO_PULLUP;
	GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;

	HAL_GPIO_Init(kern::board::DHT_DATA.port, &GPIO_InitStruct);
}

void Dht11::writePin(GPIO_PinState state)
{
	HAL_GPIO_WritePin(kern::board::DHT_DATA.port, dhtPinMask(), state);
}

GPIO_PinState Dht11::readPin() const
{
	return HAL_GPIO_ReadPin(kern::board::DHT_DATA.port, dhtPinMask());
}

bool Dht11::waitForLevel(GPIO_PinState level, uint32_t startMs)
{
	while (readPin() != level) {
		if (timedOut(startMs)) {
			return false;
		}
	}

	return true;
}

bool Dht11::timedOut(uint32_t startMs) const
{
	return (HAL_GetTick() - startMs) >= kMaxReadMs;
}

void Dht11::delayUs(uint32_t us)
{
	uint32_t ticks = us * (SystemCoreClock / 1000000u);
	uint32_t start = DWT->CYCCNT;

	while ((DWT->CYCCNT - start) < ticks) {
		__NOP();
	}
}

} // namespace kern::sensors
