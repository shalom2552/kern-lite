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

namespace kern::recorder {

void CommandHandler::sendAck()
{
    // ACK frames are empty; only the type matters to the peer.
    protocol::Frame f{};
    f.type = protocol::FrameType::Ack;
    f.len = 0;
    g_comm_link->send(f);
}

void CommandHandler::sendNack(protocol::NackCode code)
{
    // NACK payload carries the protocol-specific rejection reason.
    protocol::Frame f{};
    f.type = protocol::FrameType::Nack;
    f.len = 1;
    f.payload[0] = static_cast<uint8_t>(code);
    g_comm_link->send(f);
}

void CommandHandler::sendStatus()
{
    // Keep the status payload layout aligned with groundstation/state.py.
    protocol::Frame f{};
    f.type = protocol::FrameType::Status;
    f.len = 14;

    f.payload[0] = 0; // state: idle
    f.payload[1] = 1; // sd mounted
    f.payload[2] = 4; // file count
    f.payload[3] = 0; // current file
    // .. rest are zerod

    g_comm_link->send(f);
}

void CommandHandler::dispatch(const protocol::Frame& f)
{
    // Phase 5 only accepts STATUS for now; everything else is rejected.
    if (f.type == protocol::FrameType::CmdStatus) {
        sendStatus();
    } else {
        sendNack(protocol::NackCode::BadCommand);
    }
}

} // namespace kern::recorder

