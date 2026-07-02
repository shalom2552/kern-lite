#pragma once

#include <cstdint>
#include <cstddef>

namespace kern::protocol {

/* get data and len and return crc output */
uint32_t crc32(const uint8_t* data, size_t len);

/* return 0xFFFFFFFFu */
uint32_t crc32Begin();

/* calculate portion of data */
uint32_t crc32Update(uint32_t crc, const uint8_t* data, size_t len);

/* return crc ^ 0xFFFFFFFFu */
uint32_t crc32Finalize(uint32_t crc);

}
