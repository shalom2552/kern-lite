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

class StatusPoller(threading.Thread):
    """Periodically polls device status and validates reboot conditions."""

    def __init__(self, link, command_sender: CommandSender, device_state: DeviceStateModel, storage_model: StorageModel, poll_interval_s: float = 5.0):
        super().__init__(daemon=True)
        self.link = link
        self.command_sender = command_sender
        self.device_state = device_state
        self.storage_model = storage_model
        self.poll_interval_s = poll_interval_s
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            if self.link.connection_state == "connected":
                self.command_sender.send_status(self.link)
            time.sleep(self.poll_interval_s)

    def handle_status_reply(self, frame: Frame):
        """Must be called by the main RX loop when a STATUS reply arrives."""
        last_total_records = self.storage_model.total_records
        
        self.device_state.update_from_status(frame)
        self.storage_model.update_from_status(frame)

        if self.storage_model.total_records < (last_total_records * 0.5):
            logging.warning("REBOOT_DETECTED: total_records dropped significantly.")
            self.command_sender.send_status(self.link)
