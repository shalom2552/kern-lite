#include "state_machine.hpp"

namespace kern::recorder {

bool StateMachine::process(Event e)
{
    State next = m_state;

    switch (m_state) {
    case State::Idle:
        if (e == Event::ChecksPassed) {
            next = State::Idle;
        } else if (e == Event::UartStart) {
            next = State::Recording;
        } else if (e == Event::SdFault) {
            next = State::Fault;
        } else {
            return false;
        }
        break;

    case State::Recording:
        if (e == Event::UartStop || e == Event::ShortPress) {
            next = State::Idle;
        } else if (e == Event::SdFault) {
            next = State::Fault;
        } else {
            return false;
        }
        break;

    case State::Fault:
        if (e == Event::FaultCleared) {
            next = State::Recording;
        } else {
            return false;
        }
        break;
    }

    m_state = next;
    return true;
}

} // namespace kern::recorder
