#pragma once
#include "frame.hpp"

namespace kern::protocol {

enum class DecodeResult { NeedMore, FrameReady, CrcError, SyncError };

// Returns total bytes written to outBuf, or 0 on overflow / f.len > kMaxPayload.
size_t encode(const Frame& f, uint8_t* outBuf, size_t outSize);

class Decoder {
public:
    DecodeResult feed(uint8_t byte);
    const Frame& frame() const { return m_frame; }
    void reset();

private:
    void rearm(); // resets state machine but preserves m_frame for the caller

    enum class State {
        WaitStx, Type, LenLo, LenHi, Payload,
        Crc0, Crc1, Crc2, Crc3, WaitEtx
    };

    State m_state = State::WaitStx;
    Frame m_frame{};
    uint16_t m_payloadIdx = 0;
    uint32_t m_crc = 0;
    uint32_t m_rxCrc = 0; // little-endian CRC as received, assembled byte by byte
};

}
