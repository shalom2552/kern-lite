/*
 * StateIndicator implementation: RGB/fault LED patterns and buzzer entry
 * actions mirroring the recorder FSM.
 *
 * file: firmware/system/state_indicator.cpp
 * author: shalom2552
 * date: 2026-07-14
 */
#include "state_indicator.hpp"

#include "../hal/gpio.hpp"
#include "../hal/buzzer.hpp"
#include "board.hpp"
#include "config.hpp"

extern TIM_HandleTypeDef htim3;

namespace kern::system {

void StateIndicator::update(uint32_t now, uint8_t faultBits)
{
    updateStateLeds(faultBits);
    updateStateTones(now);
}

void StateIndicator::updateStateLeds(uint8_t faultBits)
{
    // The RGB LED mirrors the FSM state; the dedicated fault LED blinks in Fault.
    if (m_sm.isFault()) {
        m_faultBlinkOn = !m_faultBlinkOn;
        if (m_faultBlinkOn) {
            hal::gpio::set(board::LED2_RED);
        } else {
            hal::gpio::clear(board::LED2_RED);
        }
        hal::gpio::set(board::RGB_R);
        hal::gpio::clear(board::RGB_G);
        hal::gpio::clear(board::RGB_B);
        return;
    }

    hal::gpio::clear(board::LED2_RED);

    if (m_sm.isLogging()) {
        if (faultBits != 0u) {
            m_degradedBlinkOn = !m_degradedBlinkOn;
            if (m_degradedBlinkOn) {
                hal::gpio::set(board::RGB_G);
            } else {
                hal::gpio::clear(board::RGB_G);
            }
        } else {
            m_degradedBlinkOn = false;
            hal::gpio::set(board::RGB_G);
        }
        hal::gpio::clear(board::RGB_R);
        hal::gpio::clear(board::RGB_B);
        return;
    }

    hal::gpio::clear(board::RGB_R);
    hal::gpio::clear(board::RGB_G);
    hal::gpio::clear(board::RGB_B);
}

void StateIndicator::updateStateTones(uint32_t now)
{
    kern::recorder::State state = m_sm.state();

    // A5.1 entry actions: chirp on Recording, fault tone on Fault, silence on Idle.
    if (state != m_prevState) {
        m_prevState = state;

        if (state == kern::recorder::State::Recording) {
            hal::buzzer::toneOn(htim3, kern::config::kChirpFreqHz);
            m_chirpActive = true;
            m_chirpStartMs = now;
        } else if (state == kern::recorder::State::Fault) {
            hal::buzzer::toneOn(htim3, kern::config::kFaultToneFreqHz);
            m_chirpActive = false;
        } else {
            hal::buzzer::toneOff(htim3);
            m_chirpActive = false;
        }
    }

    // The chirp is a short beep, not a continuous tone; expire it here.
    if (m_chirpActive && now - m_chirpStartMs >= kern::config::kChirpMs) {
        hal::buzzer::toneOff(htim3);
        m_chirpActive = false;
    }
}

} // namespace kern::system
