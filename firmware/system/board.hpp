#pragma once

#include "stm32l4xx_hal.h"
#include <cstdint>

namespace kern::board {

/**
 * @brief Representation of a physical board GPIO pin.
 */
struct Pin { 
    GPIO_TypeDef* port; ///< GPIO Port register base address.
    uint8_t n;          ///< GPIO pin number.
};

inline constexpr Pin LED1_BLUE{GPIOC, 9}; ///< Blue LED pin
inline constexpr Pin LED2_RED {GPIOB, 8}; ///< Red LED pin
inline constexpr Pin RGB_R {GPIOC, 7};    ///< RGB Red channel pin
inline constexpr Pin RGB_G {GPIOC, 6};    ///< RGB Green channel pin
inline constexpr Pin RGB_B {GPIOC, 8};    ///< RGB Blue channel pin
inline constexpr Pin SD_CS {GPIOB, 6};    ///< SD card SPI chip select pin
inline constexpr Pin DHT_DATA {GPIOB, 5}; ///< DHT11 temperature/humidity data pin
inline constexpr Pin SW1 {GPIOA, 10};     ///< SW1 button pin
inline constexpr Pin SW2 {GPIOB, 3};      ///< SW2 button pin (connected to radiation sensor latch)
inline constexpr Pin B1 {GPIOC, 13};      ///< Blue user button pin

/**
 * @brief Mapping of analog sensors to ADC channels.
 */
enum class AdcChannel : uint32_t {

    Pot = ADC_CHANNEL_5,        ///< Potentiometer analog input channel
    Photodiode = ADC_CHANNEL_6, ///< Photodiode analog input channel
    Lm35 = ADC_CHANNEL_9,       ///< LM35 temperature analog input channel
};

}
