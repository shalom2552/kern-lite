"""
Tracks device state machine and command validation rules.

This module implements the device state model per specification section 8.6/12:
- State transitions: Idle <-> Recording, and entry to Fault state
- Transition history: Records wall-time, sequence, duration in previous state
- Command gating: Validates which commands are allowed in each state
  (e.g., START is only valid in Idle, STOP only in Recording)

The model monitors the device via STATUS frames and enforces state machine rules.

file: groundstation/state.py
author: Yair
date: 2026-06-07
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# Human-readable names for device states
STATE_NAMES = {0: "Idle", 1: "Recording", 2: "Fault"}

# Device state constants
STATE_IDLE = 0        # Device waiting for commands
STATE_RECORDING = 1   # Device actively recording sensor data
STATE_FAULT = 2       # Device in fault state (hardware or sensor failure)


@dataclass
class Transition:
    """Records a state transition event.

    Attributes:
        wall_time: Unix timestamp when transition occurred
        session_seq: Session sequence number at time of transition
        from_state: Previous state (0=Idle, 1=Recording, 2=Fault)
        to_state: New state (0=Idle, 1=Recording, 2=Fault)
        duration_in_prev: Time spent in the previous state (seconds)
    """
    wall_time: float
    session_seq: int
    from_state: int
    to_state: int
    duration_in_prev: float


class DeviceStateModel:
    """Tracks device state machine and state transitions.
    
    Monitors STATUS frames to detect state changes and records transition history.
    Validates command legality based on current state per spec 8.6.
    
    Attributes:
        state: Current device state (0=Idle, 1=Recording, 2=Fault)
        previous_state: Previous state before the last transition
        transitions: List of all Transition events recorded
        sd_mounted: Whether SD card is currently mounted
    """
    
    def __init__(self) -> None:
        """Initialize device state model in Idle state with no history."""
        self.state: int = STATE_IDLE
        self.previous_state: int | None = None
        self.transitions: list[Transition] = []
        self.sd_mounted: bool = False
        self._last_change_wall: float = time.time()  # Track state change timestamps
        self._session_seq: int = 0  # Increment on each STATUS update

    @staticmethod
    def state_name(code: int) -> str:
        """Convert numeric state code to human-readable name.
        
        Args:
            code: State code (0, 1, 2, or unknown)
        
        Returns:
            State name string (e.g., "Idle", "Recording", "Fault", or "Unknown(X)")
        """
        return STATE_NAMES.get(code, f"Unknown({code})")

    def update_from_status(self, status_frame) -> None:
        """Process a STATUS frame and detect state transitions.
        
        Extracts state and SD mount status from a 14-byte STATUS payload (spec 8.5).
        If state has changed, records a Transition event with timing information.
        
        Args:
            status_frame: Frame object with .payload (14 bytes):
                byte[0]: new device state
                byte[1]: SD card mounted flag
                bytes[2-13]: reserved/unused
        """
        payload = status_frame.payload
        new_state = payload[0]  # Device state: 0=Idle, 1=Recording, 2=Fault
        self.sd_mounted = bool(payload[1])  # SD card mounted flag
        self._session_seq += 1

        if new_state != self.state:
            # State changed: record transition with timing
            now = time.time()
            duration = now - self._last_change_wall  # How long in previous state
            self.transitions.append(Transition(
                wall_time=now,
                session_seq=self._session_seq,
                from_state=self.state,
                to_state=new_state,
                duration_in_prev=duration,
            ))
            self.previous_state = self.state
            self.state = new_state
            self._last_change_wall = now

    def command_allowed(self, cmd) -> bool:
        """Validate if a command is allowed in the current device state.
        
        Implements command gating rules per spec section 8.6:
        - START (0x01): Only when Idle
        - STOP (0x02): Only when Recording
        - STATUS (0x03): Always allowed
        - REPLAY (0x04): Only when Idle AND SD card mounted
        - ERASE (0x06): Only when Idle
        
        Args:
            cmd: Command code (int) or object with .value attribute (FrameType enum)
        
        Returns:
            True if command is valid in current state, False otherwise
        """
        # Handle both raw int and enum-like objects with .value attribute
        cmd_val = getattr(cmd, "value", cmd)
        
        if cmd_val == 0x01:  # CMD_START
            return self.state == STATE_IDLE
        if cmd_val == 0x02:  # CMD_STOP
            return self.state == STATE_RECORDING
        if cmd_val == 0x03:  # CMD_STATUS
            return True  # Always allowed
        if cmd_val == 0x04:  # CMD_REPLAY
            return self.state == STATE_IDLE and self.sd_mounted
        if cmd_val == 0x06:  # CMD_ERASE
            return self.state == STATE_IDLE
        
        return False  # Unknown command
