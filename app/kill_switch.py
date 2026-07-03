"""Persistent trading kill switch."""

import os
from pathlib import Path
from threading import Lock


class KillSwitch:
    def __init__(self, state_path=None):
        self.path = Path(
            state_path or os.getenv("KILL_SWITCH_FILE", "/config/kill-switch")
        )
        self._lock = Lock()

    def is_active(self):
        return self.path.exists()

    def engage(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("active\n", encoding="utf-8")

    def release(self):
        with self._lock:
            self.path.unlink(missing_ok=True)


kill_switch = KillSwitch()
