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

extern "C" void HAL_UART_RxCpltCallback(UART_HandleTypeDef* huart);

namespace kern::recorder {

class CommLink {
public:
    void init();
    // receive bytes via uart , save them in decoder until you get a full frame
    void feed(uint8_t byte);
    // check really fast if a frame is ready and take it
    bool poll(protocol::Frame& out);

    void send(const protocol::Frame& f);

private:
    // when u receive uart byte it get triggered , and saves a byte here m_rx_byte
    friend void ::HAL_UART_RxCpltCallback(UART_HandleTypeDef* huart);

    UART_HandleTypeDef* m_huart = nullptr;
    // instance of a decoder that can store bytes in it
    protocol::Decoder m_decoder;
    // later you store the full frame here
    protocol::Frame m_pending{};
    volatile bool m_frame_ready = false;

    uint8_t m_rx_byte = 0;

    SemaphoreHandle_t m_mutex = nullptr;
    StaticSemaphore_t m_mutexStorage;
};

// Global instance of the comm link - set by init()
extern CommLink* g_comm_link;

} // namespace kern::recorder

