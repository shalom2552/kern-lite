/**
 * byte-oriented UART transport for the KERN-LITE binary protocol.
 *
 * file: firmware/recorder/comm_link.hpp
 * author: shalom2552
 * date: 2026-05-07
 */
#pragma once

#include "../protocol/frame.hpp"
#include "../protocol/codec.hpp"
#include "stm32l4xx_hal.h"
#include "FreeRTOS.h"
#include "semphr.h"

#include <cstdint>

/**
 * @brief HAL UART RX complete callback declared for C linkage.
 * @param huart UART handle pointer.
 */
extern "C" void HAL_UART_RxCpltCallback(UART_HandleTypeDef* huart);

namespace kern::recorder {

/**
 * @brief Manages the UART-based serial communication link for protocol frame transmission and reception.
 */
class CommLink {
public:
    /**
     * @brief Initialize the UART hardware and start asynchronous RX interrupt sequence.
     */
    void init();

    /**
     * @brief Feed a received byte into the internal frame decoder.
     * @param byte The received data byte.
     */
    void feed(uint8_t byte);

    /**
     * @brief Poll the communication link to see if a valid protocol frame has been fully decoded.
     * @param out Reference to a Frame structure where the decoded frame will be stored.
     * @return true if a frame was successfully read and placed into out, false otherwise.
     */
    bool poll(protocol::Frame& out);

    /**
     * @brief Transmit a protocol frame over the UART link.
     * @param f The frame to send.
     */
    void send(const protocol::Frame& f);

private:
    friend void ::HAL_UART_RxCpltCallback(UART_HandleTypeDef* huart);

    UART_HandleTypeDef* m_huart = nullptr;

    protocol::Decoder m_decoder;
    protocol::Frame m_pending{};
    volatile bool m_frame_ready = false;

    uint8_t m_rx_byte = 0;

    SemaphoreHandle_t m_mutex = nullptr;
    StaticSemaphore_t m_mutexStorage;
};

// Global instance of the comm link - set by init()
extern CommLink* g_comm_link;

} // namespace kern::recorder

