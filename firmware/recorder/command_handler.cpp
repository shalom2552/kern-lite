/**
 * CommandHandler class implementation.
 * It handles incoming commands and sends status updates to the user.
 *
 * file: firmware/recorder/command_handler.cpp
 * author: shalom2552
 * date: 2026-05-07
 */
#include "command_handler.hpp"

#include "../protocol/frame.hpp"
#include "comm_link.hpp"
#include <cstdint>
#include <cstring>

namespace kern::recorder {

namespace {

void putU16(uint8_t* p, uint16_t v)
{
    p[0] = static_cast<uint8_t>(v & 0xFFu);
    p[1] = static_cast<uint8_t>((v >> 8) & 0xFFu);
}

void putU32(uint8_t* p, uint32_t v)
{
    p[0] = static_cast<uint8_t>(v & 0xFFu);
    p[1] = static_cast<uint8_t>((v >> 8) & 0xFFu);
    p[2] = static_cast<uint8_t>((v >> 16) & 0xFFu);
    p[3] = static_cast<uint8_t>((v >> 24) & 0xFFu);
}

uint16_t readU16(const uint8_t* p)
{
    return static_cast<uint16_t>(p[0])
        | static_cast<uint16_t>(static_cast<uint16_t>(p[1]) << 8);
}

uint32_t readU32(const uint8_t* p)
{
    return static_cast<uint32_t>(p[0])
        | (static_cast<uint32_t>(p[1]) << 8)
        | (static_cast<uint32_t>(p[2]) << 16)
        | (static_cast<uint32_t>(p[3]) << 24);
}

void sendFrame(const protocol::Frame& f)
{
    if (g_comm_link != nullptr) {
        g_comm_link->send(f);
    }
}

bool replayRecord(const storage::SensorRecord& rec, void*)
{
    protocol::Frame out{};
    out.type = protocol::FrameType::Record;
    out.len = sizeof(storage::SensorRecord);
    std::memcpy(out.payload, &rec, sizeof(storage::SensorRecord));
    sendFrame(out);
    return true;
}

} // namespace

/*
 * like init  gives you context of storage and current state*/
void CommandHandler::bind(StateMachine& sm, storage::CircularLog& box)
{
    m_sm = &sm;
    m_box = &box;
}

void CommandHandler::sendAck()
{
    // ACK frames are empty; only the type matters to the peer.
    protocol::Frame f{};
    f.type = protocol::FrameType::Ack;
    f.len = 0;
    sendFrame(f);
}

void CommandHandler::sendNack(protocol::NackCode code)
{
    // NACK payload carries the protocol-specific rejection reason.
    protocol::Frame f{};
    f.type = protocol::FrameType::Nack;
    f.len = 1;
    f.payload[0] = static_cast<uint8_t>(code);
    sendFrame(f);
}

void CommandHandler::sendStatus()
{
    // Keep the status payload layout aligned with groundstation/state.py.
    protocol::Frame f{};
    f.type = protocol::FrameType::Status;
    f.len = 14;

    if (m_sm != nullptr) {
        f.payload[0] = static_cast<uint8_t>(m_sm->state());
    } else {
        f.payload[0] = 0u;
    }

    if (m_box != nullptr && m_box->isMounted()) {
        f.payload[1] = 1u;
    } else {
        f.payload[1] = 0u;
    }

    f.payload[2] = storage::LOG_FILE_COUNT;

    if (m_box != nullptr) {
        f.payload[3] = m_box->currentFile();
    } else {
        f.payload[3] = 0u;
    }

    if (m_box != nullptr) {
        putU32(&f.payload[4], m_box->totalRecords());
    } else {
        putU32(&f.payload[4], 0u);
    }

    if (m_box != nullptr) {
        putU32(&f.payload[8], m_box->wrapCount());
    } else {
        putU32(&f.payload[8], 0u);
    }

    if (m_box != nullptr) {
        putU16(&f.payload[12], m_box->writeIndex());
    } else {
        putU16(&f.payload[12], 0u);
    }
    sendFrame(f);
}

void CommandHandler::dispatch(const protocol::Frame& f)
{
    if (m_sm == nullptr || m_box == nullptr) {
        sendNack(protocol::NackCode::StorageError);
        return;
    }

    switch (f.type) {
    case protocol::FrameType::CmdStart:
        if (!m_sm->isIdle()) {
            sendNack(protocol::NackCode::InvalidState);
            return;
        }
        m_sm->process(Event::UartStart);
        sendStatus();
        sendAck();
        break;

    case protocol::FrameType::CmdStop:
        if (!m_sm->isLogging()) {
            sendNack(protocol::NackCode::InvalidState);
            return;
        }
        m_sm->process(Event::UartStop);
        if (m_box->flushMeta() != storage::StorageStatus::Ok) {
            sendNack(protocol::NackCode::StorageError);
            return;
        }
        sendStatus();
        sendAck();
        break;

    case protocol::FrameType::CmdStatus:
        sendStatus();
        break;

    case protocol::FrameType::CmdReplay: {
        if (!m_sm->isIdle()) {
            sendNack(protocol::NackCode::InvalidState);
            return;
        }
        if (!m_box->isMounted()) {
            sendNack(protocol::NackCode::StorageError);
            return;
        }
        uint16_t n = 120;
        if (f.len >= 2) {
            n = readU16(f.payload);
        }
        storage::StorageStatus st = m_box->replayNewest(n, replayRecord, nullptr);
        if (st == storage::StorageStatus::IoError || st == storage::StorageStatus::NotMounted) {
            sendNack(protocol::NackCode::StorageError);
            return;
        }
        sendAck();
        break;
    }

    case protocol::FrameType::CmdErase: {
        if (!m_sm->isIdle()) {
            sendNack(protocol::NackCode::InvalidState);
            return;
        }
        if (f.len < 4) {
            sendNack(protocol::NackCode::BadMagic);
            return;
        }
        storage::StorageStatus st = m_box->eraseAll(readU32(f.payload));
        if (st == storage::StorageStatus::BadMagic) {
            sendNack(protocol::NackCode::BadMagic);
            return;
        }
        if (st != storage::StorageStatus::Ok) {
            sendNack(protocol::NackCode::StorageError);
            return;
        }
        sendAck();
        break;
    }

    default:
        sendNack(protocol::NackCode::BadCommand);
        break;
    }
}

} // namespace kern::recorder
