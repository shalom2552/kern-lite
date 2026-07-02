#pragma once
#include <cstdint>
#include <cstddef>

namespace kern::protocol {

inline constexpr uint8_t kStx = 0xAB;
inline constexpr uint8_t kEtx = 0xCD;
inline constexpr size_t kMaxPayload = 256;

// [STX 1][TYPE 1][LEN 2][PAYLOAD..][CRC32 4][ETX 1] => 9 bytes overhead.
// NOTE: handbook says 8; spec (ground truth) says 9. Using 9.
inline constexpr size_t kFrameOverhead = 9;
inline constexpr size_t kMaxFrameSize = kFrameOverhead + kMaxPayload; // 265

// Opcodes 0x05, 0x07, 0x11 are retired and must never be used (spec 8.3).
enum class FrameType : uint8_t {
    CmdStart  = 0x01,
    CmdStop   = 0x02,
    CmdStatus = 0x03,
    CmdReplay = 0x04,
    CmdErase  = 0x06,
    Record    = 0x10,
    Status    = 0x12,   // NOTE: spec ground truth, not 0x03 as the
                         // handbook's Phase-0 stub table implied.
    Ack       = 0x20,
    Nack      = 0x21,
};

// Per spec 8.4 — differs from the handbook's Phase-0 placeholder enum.
enum class NackCode : uint8_t {
    CrcError     = 0x01, // reserved; frame-CRC failures are dropped, not NACKed
    BadCommand   = 0x02,
    InvalidState = 0x03,
    StorageError = 0x04,
    BadMagic     = 0x06,
};

struct Frame {
    FrameType type{};
    uint8_t payload[kMaxPayload]{};
    uint16_t len = 0;
};

}
