#pragma once

#include "stm32l4xx_hal.h"
#include "../system/board.hpp"

#include <cstdint>

namespace kern::sensors {

/**
 * @brief Driver class for the DHT11 temperature and humidity sensor.
 */
class Dht11 {
public:
	/**
	 * @brief Status codes returned by the read operations.
	 */
	enum class Status {
		Ok,       ///< Read successful and checksum matched.
		Timeout,  ///< Read timed out.
		CrcError  ///< Read completed but checksum verification failed.
	};

	/**
	 * @brief Initialize the DHT11 driver.
	 * 
	 * Enables the DWT (Data Watchpoint and Trace) unit for high-resolution 
	 * microsecond delays, and sets the DHT data pin as input with pullup.
	 */
	void init();

	/**
	 * @brief Read temperature and humidity values.
	 * 
	 * Performs a critical-section raw communication sequence with the sensor,
	 * verifies the checksum, and converts values to floats.
	 * 
	 * @param tempC Reference to store the temperature in Celsius.
	 * @param humidity Reference to store the relative humidity percentage.
	 * @return Status indicating success or the specific failure reason.
	 */
	Status read(float& tempC, float& humidity);

private:
	/**
	 * @brief Configure the DHT data pin as an open-drain output.
	 */
	void pinOutput();

	/**
	 * @brief Configure the DHT data pin as an input with pullup.
	 */
	void pinInput();

	/**
	 * @brief Write a state (SET or RESET) to the DHT data pin.
	 * @param state Pin state to write.
	 */
	void writePin(GPIO_PinState state);

	/**
	 * @brief Read the current logic level of the DHT data pin.
	 * @return Current GPIO pin state (SET or RESET).
	 */
	GPIO_PinState readPin() const;

	/**
	 * @brief Wait for the DHT pin to transition to a specific level, with timeout protection.
	 * @param level Target state to wait for.
	 * @param startMs Tick timestamp when the transaction started.
	 * @return true if the level was reached, false on timeout.
	 */
	bool waitForLevel(GPIO_PinState level, uint32_t startMs);

	/**
	 * @brief Check if the read transaction has timed out relative to startMs.
	 * @param startMs Tick timestamp when the transaction started.
	 * @return true if timeout duration exceeded.
	 */
	bool timedOut(uint32_t startMs) const;

	/**
	 * @brief Delay execution for a specified number of microseconds using DWT cycle counter.
	 * @param us Microseconds to delay.
	 */
	void delayUs(uint32_t us);

	/**
	 * @brief Execute the low-level 40-bit data transmission sequence with the sensor.
	 * @param data Array to store the 5 bytes received.
	 * @return Status of the raw read operation.
	 */
	Status readRaw(uint8_t* data);

private:
	static constexpr uint32_t kMaxReadMs = 30u;
};

} // namespace kern::sensors
