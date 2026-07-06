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

namespace kern::recorder {

class CommLink {
public:
    void init();

    void feed(uint8_t byte);

    bool poll(protocol::Frame& out);

    void send(const protocol::Frame& f);

private:
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

