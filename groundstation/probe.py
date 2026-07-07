"""
manual terminal script for real board testing

file: groundstation/probe.py
author: Smallejoo
date: 2026-06-07
"""
import argparse
import time
import serial
from groundstation.link import SerialLink
from groundstation.commands import CommandSender
from groundstation.frame import Frame, FrameType, NackCode
from groundstation.telemetry import RecordDecoder


def print_status(payload: bytes):
    if len(payload) != 14:
        print(f"Bad STATUS size: {len(payload)}")
        return

    state = payload[0]
    sd_mounted = payload[1]
    file_count = payload[2]
    current_file = payload[3]

    total_records = int.from_bytes(payload[4:8], "little")
    wrap_count = int.from_bytes(payload[8:12], "little")
    records_in_file = int.from_bytes(payload[12:14], "little")

    print("STATUS:")
    print(f"state: {state}")
    print(f"sd_mounted: {sd_mounted}")
    print(f"file_count: {file_count}")
    print(f"current_file: {current_file}")
    print(f"total_records: {total_records}")
    print(f"wrap_count: {wrap_count}")
    print(f"records_in_file: {records_in_file}")


def wait_for_reply(link: SerialLink, timeout_s: float):
    # Skip the live RECORD stream and return the next command reply frame.
    start = time.time()

    while time.time() - start < timeout_s:
        frame = link.receive_frame()

        if frame is not None:
            if frame.type == FrameType.Record:
                continue
            return frame

        time.sleep(0.01)

    return None


def capture_records(link: SerialLink, duration_s: float, max_print: int):
    print(f"Capturing RECORD frames for {duration_s:.0f} s...")

    start = time.time()
    count = 0
    printed = 0
    crc_failures = 0
    seq_gaps = 0
    last_seq = None

    while time.time() - start < duration_s:
        frame = link.receive_frame()

        if frame is None:
            time.sleep(0.005)
            continue

        if frame.type != FrameType.Record:
            continue

        try:
            rec = RecordDecoder.decode(frame.payload)
        except ValueError as e:
            print(f"bad record: {e}")
            continue

        count += 1

        crc_ok = rec.record_crc_valid()
        if not crc_ok:
            crc_failures += 1

        if last_seq is not None:
            expected = (last_seq + 1) & 0xFFFF
            if rec.seq != expected:
                seq_gaps += 1
        last_seq = rec.seq

        if printed < max_print:
            printed += 1
            print(
                f"seq={rec.seq} "
                f"lm35={rec.lm35_celsius:.1f}C "
                f"dht={rec.dht_temp_celsius:.1f}C/{rec.dht_humidity:.1f}% "
                f"light={rec.light_normalized:.3f} "
                f"pot={rec.pot_normalized:.3f} "
                f"alert=0x{rec.alert_bits:02X} fault=0x{rec.fault_bits:02X} "
                f"crc={'ok' if crc_ok else 'BAD'}"
            )

    print()
    print(f"records: {count}")
    print(f"crc_failures: {crc_failures}")
    print(f"seq_gaps: {seq_gaps}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--capture", type=float, default=30.0,
                        help="seconds to capture the live RECORD stream")
    parser.add_argument("--max-print", type=int, default=10,
                        help="how many decoded records to print")
    args = parser.parse_args()

    link = SerialLink()
    commands = CommandSender()

    try:
        print("Connecting...")
        link.connect(args.port, args.baud)

        print("Sending CMD_STATUS...")
        frame = None
        for _ in range(2):
            commands.send_status(link)
            frame = wait_for_reply(link, 2.0)
            if frame is not None:
                break

        if frame is None:
            print("No STATUS response")
        elif frame.type == FrameType.Status:
            print_status(frame.payload)
            print(f"last_latency_ms: {link.last_latency_ms}")
        else:
            print(f"Unexpected frame type: {frame.type}")

        print()
        print("Sending unknown command 0xFF...")

        # This tests NACK BadCommand
        link.record_command(0xFF)
        link.send_frame(Frame(0xFF, b""))

        frame = wait_for_reply(link, 2.0)

        if frame is None:
            print("No NACK response")
        elif frame.type == FrameType.Nack and len(frame.payload) >= 1:
            print(f"NACK received, code: 0x{frame.payload[0]:02X}")

            if frame.payload[0] == NackCode.BadCommand:
                print("NACK BadCommand confirmed")
        else:
            print(f"Unexpected frame type: {frame.type}")

        print()
        if args.capture > 0:
            capture_records(link, args.capture, args.max_print)

        print()
        print("Counters:")
        print(f"tx_count: {link.tx_count}")
        print(f"rx_count: {link.rx_count}")
        print(f"crc_error_count: {link.crc_error_count}")
        print(f"sync_error_count: {link.sync_error_count}")
        print(f"nack_count: {link.nack_count}")
        print(f"nack_rate: {link.nack_rate}")
        print(f"rolling_avg_latency_ms: {link.rolling_avg_latency_ms}")

    except serial.SerialException as e:
        print(f"Could not open port {args.port}: {e}")
        print("Is the board plugged in and is the port correct?")
    finally:
        link.disconnect()
        print("Disconnected")


if __name__ == "__main__":
    main()
