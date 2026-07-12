"""
Day 5 End-of-Day hardware gate: runs the full five-command cycle against a
flashed board and checks every review item. Needs real hardware; run manually:

    python tests/hw/gate_phase5.py --port /dev/ttyACM1

file: tests/hw/gate_phase5.py
author: shalom2552
date: 2026-07-12
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from groundstation.link import SerialLink
from groundstation.commands import CommandSender
from groundstation.frame import FrameType, NackCode
from groundstation.telemetry import RecordDecoder

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def drain(link, seconds=1.0):
    # Discard stale frames (heartbeats, leftover records) from earlier runs.
    end = time.time() + seconds
    while time.time() < end:
        link.receive_frame()
        time.sleep(0.005)


def wait_reply(link, timeout=3.0, want=None, records=None):
    # Return the next non-RECORD frame (or a specific type); count records seen.
    end = time.time() + timeout
    while time.time() < end:
        f = link.receive_frame()
        if f is None:
            time.sleep(0.005)
            continue
        if f.type == FrameType.Record:
            if records is not None:
                records.append(f)
            continue
        if want is None or f.type == want:
            return f
    return None


def parse_status(p):
    return {
        "state": p[0], "sd": p[1], "files": p[2], "cur": p[3],
        "total": int.from_bytes(p[4:8], "little"),
        "wrap": int.from_bytes(p[8:12], "little"),
        "widx": int.from_bytes(p[12:14], "little"),
    }


def get_status(link, cmd, timeout=3.0):
    cmd.send_status(link)
    f = wait_reply(link, timeout=timeout, want=FrameType.Status)
    return parse_status(f.payload) if f else None


def wait_state(link, cmd, want, timeout=6.0):
    # Heartbeat STATUS frames from before a command can arrive ahead of its
    # reply, so never trust the first STATUS seen; poll until the deadline.
    end = time.time() + timeout
    while time.time() < end:
        st = get_status(link, cmd, timeout=1.0)
        if st is not None and st["state"] == want:
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--capture", type=float, default=30.0,
                        help="seconds of live stream to capture after START")
    args = parser.parse_args()

    link = SerialLink()
    cmd = CommandSender()
    link.connect(args.port, args.baud)
    print(f"connected to {args.port}")
    drain(link)

    # Baseline STATUS
    st = get_status(link, cmd)
    check("STATUS reply", st is not None, str(st))

    # START -> Recording
    cmd.send_start(link)
    f = wait_reply(link, timeout=5.0, want=FrameType.Ack)
    check("START -> ACK", f is not None)
    check("START -> STATUS state=1", wait_state(link, cmd, want=1))

    # Live stream capture: rate, CRC, sequence continuity
    print(f"capturing live stream for {args.capture:.0f} s...")
    recs, bad_crc, gaps, last = 0, 0, 0, None
    end = time.time() + args.capture
    while time.time() < end:
        f = link.receive_frame()
        if f is None:
            time.sleep(0.005)
            continue
        if f.type != FrameType.Record:
            continue
        recs += 1
        r = RecordDecoder.decode(f.payload)
        if not r.record_crc_valid():
            bad_crc += 1
        if last is not None and r.seq != ((last + 1) & 0xFFFF):
            gaps += 1
        last = r.seq
    expected = args.capture * 10
    check("live records ~10 Hz", expected * 0.85 <= recs <= expected * 1.15,
          f"records={recs}")
    check("live record CRCs valid", bad_crc == 0, f"failures={bad_crc}")
    check("seq monotonic, no gaps", gaps == 0, f"gaps={gaps}")

    # Guard: START while Recording
    cmd.send_start(link)
    f = wait_reply(link, want=FrameType.Nack)
    ok = f is not None and f.payload[0] == NackCode.InvalidState
    check("START from Recording -> NACK InvalidState", ok)

    # STOP -> Idle
    cmd.send_stop(link)
    f = wait_reply(link, timeout=5.0, want=FrameType.Ack)
    check("STOP -> ACK", f is not None)
    check("STOP -> STATUS state=0", wait_state(link, cmd, want=0))
    drain(link)

    # Guard: STOP from Idle
    cmd.send_stop(link)
    f = wait_reply(link, want=FrameType.Nack)
    ok = f is not None and f.payload[0] == NackCode.InvalidState
    check("STOP from Idle -> NACK InvalidState", ok)

    # REPLAY 60: all records back, CRC-valid, closed by ACK
    replay = []
    cmd.send_replay(link, 60)
    f = wait_reply(link, timeout=15.0, want=FrameType.Ack, records=replay)
    bad = sum(0 if RecordDecoder.decode(r.payload).record_crc_valid() else 1
              for r in replay)
    check("REPLAY 60 -> 60 records", len(replay) == 60, f"got {len(replay)}")
    check("REPLAY records CRC valid", bad == 0, f"failures={bad}")
    check("REPLAY -> ACK", f is not None)

    # ERASE: unlink + remount takes a few seconds on hardware, so both the
    # ACK wait and the post-erase STATUS poll get generous timeouts.
    cmd.send_erase(link, 0xDEADC0DE)
    f = wait_reply(link, timeout=15.0, want=FrameType.Ack)
    check("ERASE -> ACK", f is not None)
    st = None
    end = time.time() + 15
    while time.time() < end:
        st = get_status(link, cmd, timeout=5.0)
        if st is not None:
            break
    ok = st is not None and st["total"] == 0 and st["wrap"] == 0
    check("post-ERASE total_records=0 wrap=0", ok, str(st))

    print(f"\nlink counters: crc_err={link.crc_error_count} "
          f"sync_err={link.sync_error_count} rx={link.rx_count} "
          f"nack_rate={link.nack_rate:.2f}")
    link.disconnect()

    fails = sum(1 for _, ok in results if not ok)
    print(f"{'ALL GATE CHECKS PASSED' if fails == 0 else f'{fails} CHECK(S) FAILED'}"
          f" ({len(results) - fails}/{len(results)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
