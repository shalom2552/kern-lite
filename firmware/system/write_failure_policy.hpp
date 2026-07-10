/*
Storage write failure policy shared by the orchestrator and host tests.

file: firmware/system/write_failure_policy.hpp
author: shalom2552
date: 2026-07-10
*/

#pragma once

#include <cstdint>

namespace kern::system {

/**
 * @brief Counts consecutive storage failures and reports when the fault limit is reached.
 */
class WriteFailurePolicy {
public:
    explicit WriteFailurePolicy(uint8_t maxFails = 3)
        : m_maxFails(maxFails)
    {
    }

    void reset()
    {
        m_consecutiveFails = 0;
    }

    bool recordFailure()
    {
        if (m_consecutiveFails < m_maxFails) {
            ++m_consecutiveFails;
        }
        return m_consecutiveFails >= m_maxFails;
    }

    uint8_t consecutiveFails() const
    {
        return m_consecutiveFails;
    }

private:
    uint8_t m_maxFails;
    uint8_t m_consecutiveFails = 0;
};

} /* namespace kern::system */
