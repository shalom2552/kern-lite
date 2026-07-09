#pragma once

#include "../system/board.hpp"

namespace kern::hal::gpio {

/**
 * @brief Get the pin mask for a given board pin.
 * @param p The board Pin structure.
 * @return Bitmask representing the pin number.
 */
inline uint16_t mask(board::Pin p) { return static_cast<uint16_t>(1u << p.n); }

/**
 * @brief Write a HIGH (SET) state to the specified pin.
 * @param p The board Pin to set.
 */
inline void set(board::Pin p) { HAL_GPIO_WritePin(p.port, mask(p), GPIO_PIN_SET); }

/**
 * @brief Write a LOW (RESET) state to the specified pin.
 * @param p The board Pin to clear.
 */
inline void clear(board::Pin p) { HAL_GPIO_WritePin(p.port, mask(p), GPIO_PIN_RESET); }

/**
 * @brief Toggle the state of the specified pin.
 * @param p The board Pin to toggle.
 */
inline void toggle(board::Pin p) { HAL_GPIO_TogglePin(p.port, mask(p)); }

/**
 * @brief Read the current logic level of the specified pin.
 * @param p The board Pin to read.
 * @return true if the pin state is HIGH, false if it is LOW.
 */
inline bool read(board::Pin p) { return HAL_GPIO_ReadPin(p.port, mask(p)) == GPIO_PIN_SET; }

}
