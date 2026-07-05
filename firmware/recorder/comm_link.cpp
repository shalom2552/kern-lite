/**
 * byte-oriented UART transport for the KERN-LITE binary protocol.
 *
 * file: firmware/recorder/comm_link.cpp
 * author: shalom2552
 * date: 2026-05-07
 */
#include "comm_link.hpp"

#include "../protocol/codec.hpp"
#include "../protocol/frame.hpp"

#include <cstddef>
#include <cstdint>

extern UART_HandleTypeDef huart2; // global HAL handle

namespace kern::recorder {

CommLink* g_comm_link = nullptr;

void CommLink::init()
{
    m_huart = &huart2;
    m_mutex = xSemaphoreCreateMutexStatic(&m_mutexStorage);
    g_comm_link = this;
    HAL_UART_Receive_IT(m_huart, &m_rx_byte, 1);
}

void CommLink::feed(uint8_t byte)
{
    protocol::DecodeResult result = m_decoder.feed(byte);
    if (result == protocol::DecodeResult::FrameReady) {
        m_pending = m_decoder.frame();
        m_frame_ready = true;
    }
    HAL_UART_Receive_IT(m_huart, &m_rx_byte, 1); // rearm
}

bool CommLink::poll(protocol::Frame& out)
{
    if (m_frame_ready) {
        __disable_irq(); // disable interrupts
        out = m_pending;
        m_frame_ready = false;
        __enable_irq();
        return true;
    }
    return false;
}

void CommLink::send(const protocol::Frame& f)
{
    if (m_mutex == nullptr) {
        return; // init() not called yet
    }
    uint8_t buffer[protocol::kMaxFrameSize];
    xSemaphoreTake(m_mutex, portMAX_DELAY);
    size_t n = protocol::encode(f, buffer, sizeof(buffer));
    if (n > 0) {
        HAL_UART_Transmit(m_huart, buffer, n, 100); // 100ms timeout
    }
    xSemaphoreGive(m_mutex);
}

} // namespace kern::recorder
