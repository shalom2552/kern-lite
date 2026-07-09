"""
helper file that creates and sends command frames

file: commands.py
author: Smallejoo
date: 2026-06-07
"""
from groundstation.frame import Frame, FrameType


class CommandSender:
    """Builds command frames and records them before transmission."""

    def send_start(self, link):
        # Record first so latency tracking can match the reply to this command.
        link.record_command(FrameType.CmdStart)
        link.send_frame(Frame(FrameType.CmdStart, b""))

    def send_stop(self, link):
        # STOP has no payload; only the frame type differs.
        link.record_command(FrameType.CmdStop)
        link.send_frame(Frame(FrameType.CmdStop, b""))

    def send_status(self, link):
        # STATUS is the simplest probe: request state with an empty payload.
        link.record_command(FrameType.CmdStatus)
        link.send_frame(Frame(FrameType.CmdStatus, b""))

    def send_replay(self, link, n: int):
        # Replay count is encoded as a little-endian 16-bit payload.
        payload = n.to_bytes(2, byteorder="little")
        link.record_command(FrameType.CmdReplay)
        link.send_frame(Frame(FrameType.CmdReplay, payload))

    def send_erase(self, link, magic: int):
        # ERASE carries the protocol magic value as a 32-bit little-endian word.
        payload = magic.to_bytes(4, byteorder="little")
        link.record_command(FrameType.CmdErase)
        link.send_frame(Frame(FrameType.CmdErase, payload))
