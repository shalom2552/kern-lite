#pragma once

#include <cstdint>
#include <cstddef>
namespace kern::protocol {

inline constexpr uint8_t kStx = 0xAB;
inline constexpr uint8_t kEtx = 0xCD;
inline constexpr size_t kMaxPayload = 256;
inline constexpr size_t kFrameOverhead = 9;

enum class FrameType : uint8_t {
    CmdStart = 0x01,
    CmdStop = 0x02,
    CmdStatus = 0x03,
    CmdReplay = 0x04,
    CmdErase = 0x06,
    Record = 0x10,
	Status = 0x12,
    Ack = 0x20,
    Nack = 0x21,
};

enum class NackCode : uint8_t {
	CrcError = 1,
    BadCommand = 2,
    InvalidState = 3,
    StorageError = 4,
    BadMagic = 6,
};

struct Frame {
    FrameType type{};
    uint8_t payload[kMaxPayload]{};
    uint16_t len = 0;
};

}
