/*
 * StateIndicator: maps the recorder FSM state onto the RGB LED, fault LED,
 * and buzzer entry actions.
 *
 * file: firmware/system/state_indicator.hpp
 * author: shalom2552
 * date: 2026-07-14
 */
#pragma once

#include "../recorder/state_machine.hpp"

#include <cstdint>

namespace kern::system {

/*
 * @brief Drives the LED patterns and buzzer tones that mirror the FSM state.
 */
class StateIndicator {
public:
    /*
     * @brief Construct an indicator observing the recorder state machine.
     */
    explicit StateIndicator(recorder::StateMachine& sm)
        : m_sm(sm)
    {
    }

    /*
     * @brief One System task iteration: refresh LEDs and buzzer for the current state.
     * @param now Current tick in milliseconds.
     * @param faultBits Fault bits of the latest assembled record.
     */
    void update(uint32_t now, uint8_t faultBits);

private:
    /*
     * @brief Drive the RGB LED pattern for the current FSM state.
     */
    void updateStateLeds(uint8_t faultBits);

    /*
     * @brief Fire the buzzer entry actions on state transitions and expire the chirp.
     */
    void updateStateTones(uint32_t now);

    recorder::StateMachine& m_sm;

    bool m_faultBlinkOn = false;
    bool m_degradedBlinkOn = false;
    recorder::State m_prevState = recorder::State::Idle;
    bool m_chirpActive = false;
    uint32_t m_chirpStartMs = 0;
};

} // namespace kern::system
