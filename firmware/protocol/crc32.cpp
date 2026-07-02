#include "crc32.hpp"

namespace kern::protocol {

// create lookup table for the polynomial of crc32 0xEDB88320 in compile time
#include <array>
#include <cstdint>

constexpr uint32_t POLY = 0xEDB88320;

// compute crc output for every byte by the byte entry
constexpr uint32_t computeEntry(uint32_t byte)
{
    uint32_t crc = byte;

    for (int i = 0; i < 8; ++i)
    {
        if (crc & 1)
            crc = (crc >> 1) ^ POLY;
        else
            crc >>= 1;
    }

    return crc;
}

// make the table
constexpr std::array<uint32_t, 256> makeTable()
{
    std::array<uint32_t, 256> table{};

    for (uint32_t i = 0; i < 256; ++i)
        table[i] = computeEntry(i);

    return table;
}

// create the table in compile time
constexpr auto crcTable = makeTable();

uint32_t crc32(const uint8_t* data, size_t len)
{
	uint32_t crc = crc32Begin();
	crc = crc32Update(crc, data, len);
	return crc32Finalize(crc);
}

uint32_t crc32Begin()
{
	return 0xFFFFFFFFu;
}

uint32_t crc32Update(uint32_t crc, const uint8_t*, size_t)
{
    for (size_t i = 0; i < len; ++i) {
        crc = crcTable[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
    }
	return crc;
}

uint32_t crc32Finalize(uint32_t crc)
{
	return crc ^ 0xFFFFFFFFu;
}

}	// namespace kern::protocol end
