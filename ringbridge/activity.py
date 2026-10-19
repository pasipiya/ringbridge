"""Detect that you are back at the computer, which counts as acknowledging an alert."""

import re
import subprocess
import threading
import time


def idle_ms():
    """Milliseconds since the last keyboard/mouse input in the GNOME session, or None if unknown."""
    try:
        out = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
             "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
             "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"],
            capture_output=True, text=True, timeout=5).stdout
        return int(re.search(r"\d+", out).group())
    except Exception:
        return None


class AlertContext:
    """Shared state for one alert as it moves through the channel chain."""

    def __init__(self, ack_on_activity=True, stop=None):
        self.start = time.time()
        self.ack_on_activity = ack_on_activity
        self.stop = stop or threading.Event()  # set on shutdown

    def laptop_active(self):
        if self.stop.is_set():
            return True
        if not self.ack_on_activity:
            return False
        idle = idle_ms()
        return idle is not None and idle / 1000 < time.time() - self.start - 1

    def wait(self, seconds, step=1.0):
        """Sleep up to `seconds`; return True early if the user came back to the laptop."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.stop.wait(min(step, max(0, deadline - time.monotonic()))):
                return True
            if self.laptop_active():
                return True
        return False
