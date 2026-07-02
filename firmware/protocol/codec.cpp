#include "codec.hpp"
#include "crc32.hpp"
#include <cstring>

namespace kern::protocol {

size_t encode(const Frame& f, uint8_t* outBuf, size_t outSize) {
    if (f.len > kMaxPayload) return 0;
    const size_t total = kFrameOverhead + f.len;
    if (outBuf == nullptr || outSize < total) return 0;

    size_t i = 0;
    outBuf[i++] = kStx;
    outBuf[i++] = static_cast<uint8_t>(f.type);
    outBuf[i++] = static_cast<uint8_t>(f.len & 0xFF);
    outBuf[i++] = static_cast<uint8_t>((f.len >> 8) & 0xFF);

    // CRC covers TYPE + LEN(2) + PAYLOAD.
    uint32_t crc = crc32Begin();
    crc = crc32Update(crc, &outBuf[1], 3); // TYPE, LEN_LO, LEN_HI
    if (f.len > 0) {
        std::memcpy(&outBuf[i], f.payload, f.len);
        crc = crc32Update(crc, f.payload, f.len);
        i += f.len;
    }
    crc = crc32Finalize(crc);

    outBuf[i++] = static_cast<uint8_t>(crc & 0xFF);
    outBuf[i++] = static_cast<uint8_t>((crc >> 8) & 0xFF);
    outBuf[i++] = static_cast<uint8_t>((crc >> 16) & 0xFF);
    outBuf[i++] = static_cast<uint8_t>((crc >> 24) & 0xFF);
    outBuf[i++] = kEtx;

    return i; // == total
}

void Decoder::reset() {
    m_state = State::WaitStx;
    m_frame = Frame{};
    m_payloadIdx = 0;
    m_crc = 0;
    m_rxCrc = 0;
}

// Rearms the state machine for the next frame WITHOUT clearing m_frame,
// so frame() stays valid for the caller (to read the just-decoded frame)
// until the next STX starts overwriting it. Used after FrameReady/CrcError.
void Decoder::rearm() {
    m_state = State::WaitStx;
    m_payloadIdx = 0;
    m_crc = 0;
    m_rxCrc = 0;
}

DecodeResult Decoder::feed(uint8_t byte) {
    switch (m_state) {
    case State::WaitStx:
        if (byte == kStx) {
            m_frame = Frame{};
            m_payloadIdx = 0;
            m_crc = crc32Begin();
            m_state = State::Type;
        }
        // else: ignore garbage, stay in WaitStx (resync).
        return DecodeResult::NeedMore;

    case State::Type:
        m_frame.type = static_cast<FrameType>(byte);
        m_crc = crc32Update(m_crc, &byte, 1);
        m_state = State::LenLo;
        return DecodeResult::NeedMore;

    case State::LenLo:
        m_frame.len = byte; // low byte for now
        m_crc = crc32Update(m_crc, &byte, 1);
        m_state = State::LenHi;
        return DecodeResult::NeedMore;

    case State::LenHi: {
        const uint16_t lenHi = byte;
        m_frame.len = static_cast<uint16_t>(m_frame.len | (lenHi << 8));
        m_crc = crc32Update(m_crc, &byte, 1);
        if (m_frame.len > kMaxPayload) {
            reset();
            return DecodeResult::SyncError;
        }
        m_state = (m_frame.len > 0) ? State::Payload : State::Crc0;
        return DecodeResult::NeedMore;
    }

    case State::Payload:
        m_frame.payload[m_payloadIdx++] = byte;
        m_crc = crc32Update(m_crc, &byte, 1);
        if (m_payloadIdx >= m_frame.len) {
            m_state = State::Crc0;
        }
        return DecodeResult::NeedMore;

    case State::Crc0:
        m_rxCrc = byte;
        m_state = State::Crc1;
        return DecodeResult::NeedMore;

    case State::Crc1:
        m_rxCrc |= (static_cast<uint32_t>(byte) << 8);
        m_state = State::Crc2;
        return DecodeResult::NeedMore;

    case State::Crc2:
        m_rxCrc |= (static_cast<uint32_t>(byte) << 16);
        m_state = State::Crc3;
        return DecodeResult::NeedMore;

    case State::Crc3:
        m_rxCrc |= (static_cast<uint32_t>(byte) << 24);
        m_state = State::WaitEtx;
        return DecodeResult::NeedMore;

    case State::WaitEtx: {
        const uint32_t computed = crc32Finalize(m_crc);
        const uint32_t received = m_rxCrc;
        const bool etxOk = (byte == kEtx);
        rearm();
        if (!etxOk) return DecodeResult::SyncError;
        return (computed == received) ? DecodeResult::FrameReady
                                       : DecodeResult::CrcError;
    }
    }
    return DecodeResult::NeedMore;
}

}
