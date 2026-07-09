#pragma once

#include <cstddef>
#include "moving_average.hpp"
#include "threshold_detector.hpp"

namespace kern::dsp {

// DSP pipeline for single sensor channel
template <size_t N>
class Channel {
public:
	/**
	 * @brief Struct to hold the processing output of the DSP pipeline.
	 */
	struct Out {
		float raw;      ///< Raw input value.
		float filtered; ///< Filtered output value after moving average.
		ThresholdDetector::State alert; ///< Detected threshold alert state.
	};

	/**
	 * @brief Construct a Channel with a specific threshold configuration.
	 * @param cfg Configuration containing low, high thresholds and hysteresis.
	 */
	explicit Channel(ThresholdConfig cfg)
	: m_detector(cfg)
	{}

	/**
	 * @brief Default constructor for Channel.
	 */
	Channel() = default;

	/**
	 * @brief Process a raw sample through the DSP pipeline.
	 * 
	 * Updates the moving average filter and feeds the filtered value
	 * into the threshold detector to update alert states.
	 * 
	 * @param raw The new raw sensor measurement.
	 * @return Out Struct containing raw, filtered, and alert status values.
	 */
	Out process(float raw)
	{
		float filtered = m_avg.update(raw);
		auto alert = m_detector.update(filtered);
		return Out{raw, filtered, alert};
	}

	/**
	 * @brief Configure or update the threshold detector parameters.
	 * @param cfg The new threshold configuration.
	 */
	void configure(ThresholdConfig cfg)
	{
		m_detector.configure(cfg);
	}

	/**
	 * @brief Reset the internal state of the threshold detector to Normal.
	 */
	void reset()
	{
		m_detector.reset();
	}

	/**
	 * @brief Get the current filtered value of the moving average.
	 * @return Current moving average value.
	 */
	float filtered() const
	{
		return m_avg.value();
	}

	/**
	 * @brief Get the current threshold alert state.
	 * @return Current State (Normal, LowAlert, HighAlert).
	 */
	ThresholdDetector::State alert() const
	{
		return m_detector.state();
	}

	/**
	 * @brief Check if there is an active alert (Low or High).
	 * 
	 * Note: An alert can only be triggered if the moving average buffer is full.
	 * 
	 * @return true if an alert is active, false otherwise.
	 */
	bool isAlert() const
	{
		if (!m_avg.full()) {
			return false;
		}
		return m_detector.isAlert();
	}

private:
	MovingAverage<float, N> m_avg;
	ThresholdDetector m_detector;
};

} // namespace kern::channel

