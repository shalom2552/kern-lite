#pragma once
#include "frame.hpp"

namespace kern::protocol {

/**
 * @brief Results returned by the protocol decoder.
 */
enum class DecodeResult { NeedMore, FrameReady, CrcError, SyncError };

/* Returns total bytes written to outBuf, or 0 on overflow / f.len > kMaxPayload. */
size_t encode(const Frame& f, uint8_t* outBuf, size_t outSize);

/**
 * @brief Protocol frame decoder class.
 * 
 * Assembles input bytes into complete protocol Frames using a state machine
 * and calculates/verifies CRC32 values.
 */
class Decoder {
public:
    /**
     * @brief Feed a single byte to the decoder state machine.
     * @param byte The incoming byte from the communication interface.
     * @return The decode result status (e.g. FrameReady, NeedMore, CrcError, SyncError).
     */
    DecodeResult feed(uint8_t byte);

    /**
     * @brief Get the decoded Frame once DecodeResult::FrameReady is returned.
     * @return Reference to the decoded Frame.
     */
    const Frame& frame() const;

    /**
     * @brief Reset the decoder state machine and internal frame state completely.
     */
    void reset();

private:
    /* resets state machine but preserves m_frame for the caller */
    void rearm();

    enum class State {
        WaitStx, Type, LenLo, LenHi, Payload,
        Crc0, Crc1, Crc2, Crc3, WaitEtx
    };

private:
    State m_state = State::WaitStx;
    Frame m_frame{};
    uint16_t m_payloadIdx = 0;
    uint32_t m_crc = 0;
    uint32_t m_rxCrc = 0; // little-endian CRC as received, assembled byte by byte
};

}
