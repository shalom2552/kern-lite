/*
converts frames to bytes and vice versa

*/
#pragma once
#include "frame.hpp"

namespace kern::protocol {

enum class DecodeResult { NeedMore, FrameReady, CrcError, SyncError };

// Returns total bytes written to outBuf, or 0 on overflow / f.len > kMaxPayload.
// takes a frame encodes it into bytes and saves it in outBuf
size_t encode(const Frame& f, uint8_t* outBuf, size_t outSize);

class Decoder {
public:
	//creates the frame byte by byte . it gets bytes , and places them
									  // in the correct order to create a frame
									  // it got an internal frame
    DecodeResult feed(uint8_t byte);
    const Frame& frame() const;
    void reset();

private:
    // resets state machine but preserves m_frame for the caller
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
