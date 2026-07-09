#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace kern::dsp {

template  <typename T, size_t N>
class MovingAverage {
	static_assert(N > 0, "Window size must be > 0");
public:

	/**
	 * @brief Construct a MovingAverage filter and reset internal state/buffer.
	 */
	MovingAverage()
	{
		reset();
	}

	/**
	 * @brief Update the filter with a new sample.
	 * 
	 * Adds the new sample to the circular buffer, subtracts the oldest
	 * sample, updates the sum, and returns the computed moving average.
	 * 
	 * @param sample The new sample value.
	 * @return The new computed moving average.
	 */
	T update(T sample)
	{
		m_sum -= m_buf[m_head];
		m_buf[m_head] = sample;
		m_sum += sample;
		m_head = (m_head + 1) % N;
		if (m_count < N) {
			++m_count;
		}
		return value();
	}

	/**
	 * @brief Get the current filtered average value.
	 * @return The calculated average, or default T{} if no samples have been received.
	 */
	T value() const
	{
		if (m_count == 0) {
			return T{};
		}
		return m_sum / static_cast<T>(m_count);
	}

	/**
	 * @brief Clear the circular buffer and reset sum, head, and count.
	 */
	void reset()
	{
		memset(m_buf, 0, sizeof(m_buf));
		m_sum = T{};
		m_head = 0;
		m_count = 0;
	}

	/**
	 * @brief Get the number of samples currently stored in the buffer.
	 * @return The sample count.
	 */
	size_t count() const
	{
		return m_count;
	}

	/**
	 * @brief Check if the moving average window is completely filled.
	 * @return true if m_count == N, false otherwise.
	 */
	bool full() const
	{
		return m_count == N;
	}

private:
	T m_buf[N];
	T m_sum;
	size_t m_head;
	size_t m_count;

};

} //namespace kern::dsp



