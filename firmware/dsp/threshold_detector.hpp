#pragma once

#include <cstdint>

namespace kern::dsp {

/**
 * @brief Configuration parameters for the threshold detector.
 */
struct ThresholdConfig {
	float lo;		  // LowAlert below this
	float hi; 		  // HighAlert above this
	float hysteresis; // must move this far back inside bounds to remove alert
};


/**
 * the over all stats/configuration for each sensor .
 * and where is he depending on the volt
 */
/**
 * @brief Class for detecting if a value crosses thresholds, with hysteresis.
 */
  
class ThresholdDetector {
public:
	/**
	 * @brief Alert states.
	 */
	enum class State : uint8_t {
		Normal,
		LowAlert,
		HighAlert
	};

	/**
	 * @brief Constructor with threshold configuration.
	 * @param cfg The threshold configuration.
	 */
	explicit ThresholdDetector(ThresholdConfig cfg)
	: m_cfg(cfg)
	, m_state(State::Normal)
	{}

	/**
	 * @brief Default constructor setting all thresholds to 0.
	 */
	ThresholdDetector()
	: m_cfg{0.0f, 0.0f, 0.0f}
	, m_state(State::Normal)
	{}

	/**
	 * @brief Update the detector state with a new value.
	 * 
	 * Transition logic takes hysteresis into account when reverting to Normal.
	 * 
	 * @param v The value to evaluate.
	 * @return The updated State.
	 */
	State update(float v)
	{
		switch (m_state) {
			case State::Normal:
				if (v > m_cfg.hi) {
					m_state = State::HighAlert;
				}
				else if (v < m_cfg.lo) {
					m_state = State::LowAlert;
				}
				break;
			case State::HighAlert:
				if (v < m_cfg.hi - m_cfg.hysteresis) {
					m_state = (v < m_cfg.lo) ? State::LowAlert : State::Normal;
				}
				break;
			case State::LowAlert:
				if (v > m_cfg.lo + m_cfg.hysteresis) {
					m_state = (v > m_cfg.hi) ? State::HighAlert : State::Normal;
				}
				break;
		}
		return m_state;
	}

	/**
	 * @brief Get the current state of the detector.
	 * @return Current alert state.
	 */
	State state() const
	{
		return m_state;
	}

	/**
	 * @brief Reset detector state to Normal.
	 */
	void reset()
	{
		m_state = State::Normal;
	}

	/**
	 * @brief Reconfigure thresholds and reset detector state to Normal.
	 * @param cfg The new threshold configuration.
	 */
	void configure(ThresholdConfig cfg)
	{
		m_cfg = cfg;
		m_state = State::Normal;
	}

	/**
	 * @brief Check if currently in an alert state.
	 * @return true if state is not Normal.
	 */
	bool isAlert() const
	{
		return m_state != State::Normal;
	}

private:
	ThresholdConfig m_cfg;
	State m_state;
};

} // namespace kern::dsp

