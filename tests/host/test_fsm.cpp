/*
Host tests for Day 5 Member A firmware work: recorder FSM, command guards,
and the SD write failure policy described for the orchestrator.

file: tests/host/test_fsm.cpp
author: shalom2552
date: 2026-07-09
*/

#include "../../firmware/recorder/state_machine.hpp"
#include "../../firmware/recorder/command_handler.hpp"
#include "../../firmware/recorder/comm_link.hpp"
#include "../../firmware/protocol/frame.hpp"
#include "../../firmware/storage/circular_log.hpp"
#include "../../firmware/system/write_failure_policy.hpp"
#include "fatfs_shim/ff.h"

#include <cstdio>
#include <cstdint>
#include <vector>

using kern::protocol::Frame;
using kern::protocol::FrameType;
using kern::protocol::NackCode;
using kern::recorder::CommandHandler;
using kern::recorder::CommLink;
using kern::recorder::Event;
using kern::recorder::State;
using kern::recorder::StateMachine;
using kern::storage::CircularLog;
using kern::system::WriteFailurePolicy;

static int g_failures = 0;
static std::vector<Frame> g_sentFrames;

#define CHECK(cond) do { \
    if (!(cond)) { \
        std::printf("FAIL: %s line %d\n", #cond, __LINE__); \
        ++g_failures; \
    } \
} while (0)

namespace kern::recorder {

CommLink* g_comm_link = nullptr;

void CommLink::send(const kern::protocol::Frame& f)
{
    g_sentFrames.push_back(f);
}

} // namespace kern::recorder

static void freshRoot(const char* name)
{
    char dir[256];
    std::snprintf(dir, sizeof(dir), "./_ffroot_%s", name);
    ff_test_set_root(dir);
    f_unlink("0:LOG00.BIN");
    f_unlink("0:LOG01.BIN");
    f_unlink("0:LOG02.BIN");
    f_unlink("0:LOG03.BIN");
    f_unlink("0:META.BIN");
}

static void resetCapture(CommLink& link)
{
    g_sentFrames.clear();
    kern::recorder::g_comm_link = &link;
}

static Frame command(FrameType type)
{
    Frame f{};
    f.type = type;
    return f;
}

static void expectNack(NackCode code)
{
    CHECK(g_sentFrames.size() == 1);
    if (g_sentFrames.size() == 1) {
        CHECK(g_sentFrames[0].type == FrameType::Nack);
        CHECK(g_sentFrames[0].len == 1);
        CHECK(g_sentFrames[0].payload[0] == static_cast<uint8_t>(code));
    }
}

static void test_valid_fsm_pairs()
{
    {
        StateMachine sm;
        CHECK(sm.process(Event::ChecksPassed));
        CHECK(sm.state() == State::Idle);
    }
    {
        StateMachine sm;
        CHECK(sm.process(Event::UartStart));
        CHECK(sm.state() == State::Recording);
    }
    {
        StateMachine sm;
        CHECK(sm.process(Event::SdFault));
        CHECK(sm.state() == State::Fault);
    }
    {
        StateMachine sm;
        CHECK(sm.process(Event::UartStart));
        CHECK(sm.process(Event::UartStop));
        CHECK(sm.state() == State::Idle);
    }
    {
        StateMachine sm;
        CHECK(sm.process(Event::UartStart));
        CHECK(sm.process(Event::ShortPress));
        CHECK(sm.state() == State::Idle);
    }
    {
        StateMachine sm;
        CHECK(sm.process(Event::UartStart));
        CHECK(sm.process(Event::SdFault));
        CHECK(sm.state() == State::Fault);
    }
    {
        StateMachine sm;
        CHECK(sm.process(Event::SdFault));
        CHECK(sm.process(Event::FaultCleared));
        CHECK(sm.state() == State::Recording);
    }

    std::printf("[OK] valid FSM pairs\n");
}

static void test_cmd_start_from_recording_nacks_invalid_state()
{
    freshRoot("fsm_cmd_start");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    CHECK(sm.process(Event::UartStart));
    handler.dispatch(command(FrameType::CmdStart));

    expectNack(NackCode::InvalidState);
    std::printf("[OK] CMD_START from Recording guard\n");
}

static void test_cmd_stop_from_idle_nacks_invalid_state()
{
    freshRoot("fsm_cmd_stop");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    handler.dispatch(command(FrameType::CmdStop));

    expectNack(NackCode::InvalidState);
    std::printf("[OK] CMD_STOP from Idle guard\n");
}

static void test_cmd_erase_from_recording_nacks_invalid_state()
{
    freshRoot("fsm_cmd_erase_recording");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    CHECK(sm.process(Event::UartStart));
    Frame f = command(FrameType::CmdErase);
    f.len = 4;
    handler.dispatch(f);

    expectNack(NackCode::InvalidState);
    std::printf("[OK] CMD_ERASE from Recording guard\n");
}

static void test_cmd_erase_wrong_magic_nacks_bad_magic()
{
    freshRoot("fsm_cmd_erase_magic");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    Frame f = command(FrameType::CmdErase);
    f.len = 4;
    f.payload[0] = 0x00;
    f.payload[1] = 0x00;
    f.payload[2] = 0x00;
    f.payload[3] = 0x00;
    handler.dispatch(f);

    expectNack(NackCode::BadMagic);
    std::printf("[OK] CMD_ERASE wrong magic guard\n");
}

static void test_cmd_replay_from_fault_nacks_invalid_state()
{
    freshRoot("fsm_cmd_replay_fault");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    CHECK(sm.process(Event::SdFault));
    handler.dispatch(command(FrameType::CmdReplay));

    expectNack(NackCode::InvalidState);
    std::printf("[OK] CMD_REPLAY from Fault guard\n");
}

static void test_cmd_start_happy_path_status_then_ack()
{
    freshRoot("fsm_cmd_start_ok");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    handler.dispatch(command(FrameType::CmdStart));

    CHECK(sm.state() == State::Recording);
    CHECK(g_sentFrames.size() == 2);
    if (g_sentFrames.size() == 2) {
        CHECK(g_sentFrames[0].type == FrameType::Status);
        CHECK(g_sentFrames[0].payload[0] == 1);
        CHECK(g_sentFrames[1].type == FrameType::Ack);
    }
    std::printf("[OK] CMD_START happy path\n");
}

static void test_cmd_stop_happy_path_transitions_to_idle()
{
    freshRoot("fsm_cmd_stop_ok");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    CHECK(sm.process(Event::UartStart));
    handler.dispatch(command(FrameType::CmdStop));

    // The transition must happen even when the meta flush cannot run
    // (box unmounted here); recovery rebuilds the position on mount.
    CHECK(sm.state() == State::Idle);
    CHECK(g_sentFrames.size() == 2);
    if (g_sentFrames.size() == 2) {
        CHECK(g_sentFrames[0].type == FrameType::Status);
        CHECK(g_sentFrames[0].payload[0] == 0);
        CHECK(g_sentFrames[1].type == FrameType::Ack);
    }
    std::printf("[OK] CMD_STOP happy path\n");
}

static void test_unknown_command_nacks_bad_command()
{
    freshRoot("fsm_cmd_unknown");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    Frame f{};
    f.type = static_cast<FrameType>(0xFF);
    handler.dispatch(f);

    expectNack(NackCode::BadCommand);
    std::printf("[OK] unknown command guard\n");
}

static void test_cmd_erase_short_payload_nacks_bad_magic()
{
    freshRoot("fsm_cmd_erase_short");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    Frame f = command(FrameType::CmdErase);
    f.len = 3;
    handler.dispatch(f);

    expectNack(NackCode::BadMagic);
    std::printf("[OK] CMD_ERASE short payload guard\n");
}

static void test_cmd_replay_unmounted_nacks_storage_error()
{
    freshRoot("fsm_cmd_replay_unmounted");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    handler.dispatch(command(FrameType::CmdReplay));

    expectNack(NackCode::StorageError);
    std::printf("[OK] CMD_REPLAY unmounted guard\n");
}

static void test_status_payload_layout()
{
    freshRoot("fsm_status_layout");
    CommLink link;
    resetCapture(link);
    StateMachine sm;
    CircularLog box;
    CommandHandler handler;
    handler.bind(sm, box);

    handler.dispatch(command(FrameType::CmdStatus));

    CHECK(g_sentFrames.size() == 1);
    if (g_sentFrames.size() == 1) {
        const Frame& f = g_sentFrames[0];
        CHECK(f.type == FrameType::Status);
        CHECK(f.len == 14);
        CHECK(f.payload[0] == 0); // Idle
        CHECK(f.payload[1] == 0); // not mounted
        CHECK(f.payload[2] == kern::storage::LOG_FILE_COUNT);
    }
    std::printf("[OK] STATUS payload layout\n");
}

static void test_write_failure_policy_faults_on_third_consecutive_failure()
{
    StateMachine sm;
    WriteFailurePolicy policy;

    CHECK(sm.process(Event::UartStart));
    CHECK(sm.state() == State::Recording);

    CHECK(!policy.recordFailure());
    CHECK(sm.state() == State::Recording);
    CHECK(policy.consecutiveFails() == 1);

    CHECK(!policy.recordFailure());
    CHECK(sm.state() == State::Recording);
    CHECK(policy.consecutiveFails() == 2);

    if (policy.recordFailure()) {
        sm.process(Event::SdFault);
    }
    CHECK(sm.state() == State::Fault);
    CHECK(policy.consecutiveFails() == 3);

    CHECK(policy.recordFailure());
    CHECK(policy.consecutiveFails() == 3);

    std::printf("[OK] write failure policy\n");
}

int main()
{
    test_valid_fsm_pairs();
    test_cmd_start_from_recording_nacks_invalid_state();
    test_cmd_stop_from_idle_nacks_invalid_state();
    test_cmd_erase_from_recording_nacks_invalid_state();
    test_cmd_erase_wrong_magic_nacks_bad_magic();
    test_cmd_replay_from_fault_nacks_invalid_state();
    test_cmd_start_happy_path_status_then_ack();
    test_cmd_stop_happy_path_transitions_to_idle();
    test_unknown_command_nacks_bad_command();
    test_cmd_erase_short_payload_nacks_bad_magic();
    test_cmd_replay_unmounted_nacks_storage_error();
    test_status_payload_layout();
    test_write_failure_policy_faults_on_third_consecutive_failure();

    if (g_failures == 0) {
        std::printf("ALL FSM TESTS PASSED\n");
        return 0;
    }
    std::printf("%d TEST(S) FAILED\n", g_failures);
    return 1;
}
