"""Turns Events into phone alerts: schedule, cooldown, one alert at a time, channel fallback."""

import logging
import shutil
import subprocess
import threading
import time

from ringbridge.activity import AlertContext
from ringbridge.channels import CHANNELS, Outcome
from ringbridge.schedule import in_shift

log = logging.getLogger("ringbridge")


class Dispatcher:
    def __init__(self, cfg, ack_on_activity=None):
        self.cfg = cfg
        alert = cfg["alert"]
        self.chain = [CHANNELS[name](cfg["channels"][name]) for name in alert["channels"]]
        self.cooldown = alert.get("cooldown_seconds", 120)
        self.include_sender = alert.get("include_sender", True)
        self.escalate = alert.get("escalate_unacknowledged", False)
        self.ack_on_activity = (alert.get("ack_on_laptop_activity", False)
                                if ack_on_activity is None else ack_on_activity)
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.busy = False
        self.last_alert = float("-inf")
        self.missed = 0  # events that arrived while an alert was already running

    def submit(self, event):
        """Called by sources (any thread). Starts an alert in the background if appropriate."""
        if not in_shift(self.cfg["schedule"]):
            log.info("%s from %r outside shift, ignored", event.source, event.sender)
            return False
        with self.lock:
            if self.busy:
                self.missed += 1
                log.info("%s from %r while already alerting, ignored", event.source, event.sender)
                return False
            wait = self.last_alert + self.cooldown - time.monotonic()
            if wait > 0:
                log.info("%s from %r during cooldown (%ds left), ignored", event.source, event.sender, wait)
                return False
            self.busy = True
            self.last_alert = time.monotonic()
        threading.Thread(target=self._run, args=(event.alert_text(self.include_sender),),
                         name="alert", daemon=True).start()
        return True

    def _run(self, text):
        try:
            self.alert(text)
        except Exception:
            log.exception("Alert crashed")
        finally:
            with self.lock:
                self.busy = False
                if self.missed:
                    log.info("%d more message(s) arrived during that alert", self.missed)
                    self.missed = 0

    def alert(self, text):
        """Run the channel chain. Returns the final Outcome."""
        ctx = AlertContext(self.ack_on_activity, self.stop)
        outcome = Outcome.FAILED
        for i, channel in enumerate(self.chain):
            if i:
                log.warning("Falling back to channel '%s'", channel.name)
            try:
                outcome = channel.alert(text, ctx)
            except Exception:
                log.exception("Channel '%s' crashed", channel.name)
                outcome = Outcome.FAILED
            log.info("Channel '%s': %s", channel.name, outcome.value)
            if outcome is Outcome.ACKNOWLEDGED:
                break
            if outcome is Outcome.UNACKNOWLEDGED and not self.escalate:
                break
        if outcome is Outcome.FAILED:
            log.error("ALL CHANNELS FAILED: you were not alerted (%s)", text)
            local_warning(text)
        return outcome


def local_warning(text):
    """Last resort: a critical popup on this computer, so a failure is at least visible."""
    if not shutil.which("notify-send"):
        return
    try:
        subprocess.run(["notify-send", "-u", "critical", "-a", "ringbridge",
                        "ringbridge could not reach your phone", text], timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass
