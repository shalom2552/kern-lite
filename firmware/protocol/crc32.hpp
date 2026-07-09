#pragma once

#include <cstdint>
#include <cstddef>

namespace kern::protocol {

/**
 * @brief Calculate the CRC32 of a data block in a single call.
 * 
 *  get data and len and return crc output
 * 
 * @param data Pointer to the buffer.
 * @param len Length of the buffer in bytes.
 * @return Calculated CRC32 value.
 */
uint32_t crc32(const uint8_t* data, std::size_t len);

/**
 * @brief Initialize a CRC32 calculation stream.
 * @return The initial CRC state value.
 */
uint32_t crc32Begin();

/**
 * @brief Update an active CRC32 calculation with a chunk of data.
 * 
 * @param crc The current intermediate CRC state.
 * @param data Pointer to the chunk buffer.
 * @param len Length of the chunk in bytes.
 * @return The updated intermediate CRC state.
 */
uint32_t crc32Update(uint32_t crc, const uint8_t* data, std::size_t len);

/**
 * @brief Finalize the CRC32 calculation by inverting the bits.
 * 
 * @param crc The final intermediate CRC state.
 * @return The finalized CRC32 checksum.
 */
uint32_t crc32Finalize(uint32_t crc);

}
