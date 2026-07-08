#pragma once
#include <cstdint>
#include <cstddef>

namespace kern::protocol {

inline constexpr uint8_t kStx = 0xAB; ///< Start of Text marker
inline constexpr uint8_t kEtx = 0xCD; ///< End of Text marker
inline constexpr size_t kMaxPayload = 256; ///< Maximum allowed payload size in bytes
inline constexpr size_t kFrameOverhead = 9; ///< Protocol frame overhead bytes (STX + Type + LenLo + LenHi + CRC32 + ETX)
inline constexpr size_t kMaxFrameSize = kFrameOverhead + kMaxPayload; ///< Maximum total size of a frame

/* Opcodes 0x05, 0x07, 0x11 are retired and must never be used */
/**
 * @brief Identifiers for command and record frame types.
 */
enum class FrameType : uint8_t {
    CmdStart  = 0x01, ///< Command to start logging
    CmdStop   = 0x02, ///< Command to stop logging
    CmdStatus = 0x03, ///< Command to request status
    CmdReplay = 0x04, ///< Command to replay logs
    CmdErase  = 0x06, ///< Command to erase logs
    Record    = 0x10, ///< Sensor data record frame
    Status    = 0x12, ///< Device status report frame
    Ack       = 0x20, ///< Acknowledge command receipt
    Nack      = 0x21, ///< Negative acknowledge command receipt
};

/**
 * @brief Negative Acknowledge (NACK) reason codes.
 */
enum class NackCode : uint8_t {
    CrcError     = 0x01, ///< Frame CRC check failed
    BadCommand   = 0x02, ///< Unknown or unsupported frame type
    InvalidState = 0x03, ///< Command not allowed in current state
    StorageError = 0x04, ///< Error performing storage write/erase operations
    BadMagic     = 0x06, ///< Erase command magic number did not match
};

/**
 * @brief Structure representing a parsed or to-be-transmitted protocol frame.
 */
struct Frame {
    FrameType type{}; ///< Type/opcode of the frame
    uint8_t payload[kMaxPayload]{}; ///< Payload bytes buffer
    uint16_t len = 0; ///< Number of valid bytes in the payload
};

}
