"""
helper file that creates and sends command frames

file: tests/gs/test_cross_vectors.py
author: Smallejoo
date: 2026-06-07
"""
from groundstation.frame import Frame, FrameType


class CommandSender:
    def send_start(self, link):
        link.record_command(FrameType.CmdStart)
        link.send_frame(Frame(FrameType.CmdStart, b""))

    def send_stop(self, link):
        link.record_command(FrameType.CmdStop)
        link.send_frame(Frame(FrameType.CmdStop, b""))

    def send_status(self, link):
        link.record_command(FrameType.CmdStatus)
        link.send_frame(Frame(FrameType.CmdStatus, b""))

    def send_replay(self, link, n: int):
        payload = n.to_bytes(2, byteorder="little")
        link.record_command(FrameType.CmdReplay)
        link.send_frame(Frame(FrameType.CmdReplay, payload))

    def send_erase(self, link, magic: int):
        payload = magic.to_bytes(4, byteorder="little")
        link.record_command(FrameType.CmdErase)
        link.send_frame(Frame(FrameType.CmdErase, payload))
