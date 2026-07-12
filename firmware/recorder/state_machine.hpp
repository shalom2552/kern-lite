/*
Three-state recorder FSM: Idle, Recording, Fault.

file: firmware/recorder/state_machine.hpp
author: Smallejoo
date: 2026-07-08
*/

#pragma once

#include <cstdint>

namespace kern::recorder {

/**
 * @brief Device recorder states.
 */
enum class State : uint8_t { Idle = 0, Recording = 1, Fault = 2 };

/**
 * @brief Recorder state transition events.
 */
enum class Event : uint8_t { ChecksPassed, SdFault, UartStart, UartStop, ShortPress, FaultCleared };

/**
 * @brief State machine managing the recorder lifecycle state transitions.
 */
class StateMachine {
public:
    /**
     * @brief Process an incoming event to trigger a state transition.
     * @param e The event to trigger.
     * @return true if the state transition was valid and completed, false if not allowed.
     */
    bool process(Event e);

    /**
     * @brief Get the current recorder state.
     * @return The current state enum.
     */
    State state() const { return m_state; }

    /**
     * @brief Check if the machine is in the Idle state.
     * @return true if state is Idle.
     */
    bool isIdle() const { return m_state == State::Idle; }

    /**
     * @brief Check if the machine is in the Recording state.
     * @return true if state is Recording.
     */
    bool isLogging() const { return m_state == State::Recording; }

    /**
     * @brief Check if the machine is in the Fault state.
     * @return true if state is Fault.
     */
    bool isFault() const { return m_state == State::Fault; }

private:
    State m_state = State::Idle;
};

} // namespace kern::recorder
