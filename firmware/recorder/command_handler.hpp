/**
 * Constructs and sends protocol frames in response to received commands.
 * Reads live recorder state and storage values to handle commands.
 *
 * file: firmware/recorder/command_handler.hpp
 * author: shalom2552
 * date: 2026-05-07
 */
#pragma once

#include "../protocol/frame.hpp"
#include "../storage/circular_log.hpp"
#include "state_machine.hpp"

namespace kern::recorder {

class CommandHandler {
public:
    /**
     * Bind live recorder state and storage used by command handlers.
     */
    void bind(StateMachine& sm, storage::CircularLog& box);

    /**
     * Sends a zero-payload ACK frame.
     */
    void sendAck();

    /**
     * Sends a 1 byte NACK frame.
     *
     * @param code The error code to send.
     */
    void sendNack(protocol::NackCode code);

    /**
     * Sends a 14 byte STATUS frame reporting device state:
     *  state, sd_mounted, file_count, current_file, total_records,
     *  wrap_count, records_in_file.
     */
    void sendStatus();

    /**
     * Handles CMD_STATUS -> sendStatus();
     *  any other type -> sendNack(BadCommand).
     *
     * @param f The incoming frame to handle.
     */
    void dispatch(const protocol::Frame& f);

private:
    StateMachine* m_sm = nullptr;
    storage::CircularLog* m_box = nullptr;
};

} // namespace kern::recorder
