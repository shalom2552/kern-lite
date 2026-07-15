"""
Entry point: python -m dashboard

Installs SIGINT/SIGTERM handlers so Ctrl+C (or a kill) shuts the dashboard
down cleanly: serial port closed, reconnect thread stopped, session files
flushed, alert log and timeline written into the session directory.

file: dashboard/__main__.py
author: shalom2552
date: 2026-07-15
"""
from __future__ import annotations

import signal

from dashboard.app import GroundStationApp

SIGNAL_TICK_MS = 200


def main() -> None:
    app = GroundStationApp()

    def on_signal(_signum, _frame) -> None:
        # Runs on the main thread between tk events; hand off to tk so the
        # teardown happens inside the mainloop rather than mid-callback.
        app.after(0, app.shutdown)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    def signal_tick() -> None:
        # tkinter only services Python signal handlers while processing
        # events; this idle tick guarantees Ctrl+C is noticed promptly even
        # when the UI is otherwise quiet.
        if not app._shutting_down:
            app.after(SIGNAL_TICK_MS, signal_tick)

    app.after(SIGNAL_TICK_MS, signal_tick)

    try:
        app.mainloop()
    finally:
        # Covers exception paths out of mainloop: port and session files are
        # closed exactly once (shutdown is idempotent).
        app.shutdown()


if __name__ == "__main__":
    main()
