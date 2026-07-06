"""
manual terminal script for real board testing

file: groundstation/probe.py
author: Smallejoo
date: 2026-06-07
"""
import argparse
import time
from groundstation.link import SerialLink
from groundstation.commands import CommandSender
from groundstation.frame import Frame, FrameType, NackCode


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


def wait_for_frame(link: SerialLink, timeout_s: float):
    start = time.time()

    while time.time() - start < timeout_s:
        frame = link.receive_frame()

        if frame is not None:
            return frame

        time.sleep(0.01)

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    link = SerialLink()
    commands = CommandSender()

    try:
        print("Connecting...")
        link.connect(args.port, args.baud)

        print("Sending CMD_STATUS...")
        commands.send_status(link)

        frame = wait_for_frame(link, 2.0)
        
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

        frame = wait_for_frame(link, 2.0)

        if frame is None:
            print("No NACK response")
        elif frame.type == FrameType.Nack and len(frame.payload) >= 1:
            print(f"NACK received, code: 0x{frame.payload[0]:02X}")

            if frame.payload[0] == NackCode.BadCommand:
                print("NACK BadCommand confirmed")
        else:
            print(f"Unexpected frame type: {frame.type}")

        print()
        print("Counters:")
        print(f"tx_count: {link.tx_count}")
        print(f"rx_count: {link.rx_count}")
        print(f"crc_error_count: {link.crc_error_count}")
        print(f"sync_error_count: {link.sync_error_count}")
        print(f"nack_count: {link.nack_count}")
        print(f"nack_rate: {link.nack_rate}")
        print(f"rolling_avg_latency_ms: {link.rolling_avg_latency_ms}")

    finally:
        link.disconnect()
        print("Disconnected")


if __name__ == "__main__":
    main()
