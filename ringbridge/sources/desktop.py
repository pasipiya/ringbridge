"""Desktop notifications (freedesktop D-Bus): Teams, Slack, ... any app that shows a popup.

One passive D-Bus monitor is shared by every `desktop` source; each source matches its own app.
Needs no access to the app itself, no admin rights and no API keys.
"""

import logging
import re
import threading
import time

from ringbridge.events import Event, strip_markup
from ringbridge.sources.base import Source, register

log = logging.getLogger("ringbridge.source.desktop")

# Ready-made match patterns for common apps; use with `preset = "<name>"`.
# ompifgpmddkgmclendfeacglnodjjndh is the Chrome app id of the Teams PWA.
PRESETS = {
    "teams": [r"teams\.microsoft", r"teams\.cloud\.microsoft", r"teams\.live\.com",
              r"microsoft teams", r"teams-for-linux", r"ompifgpmddkgmclendfeacglnodjjndh"],
    "slack": [r"\bslack\b", r"app\.slack\.com"],
}


class _Monitor:
    """Single D-Bus monitor that fans notifications out to all desktop sources."""

    def __init__(self):
        self.sources = []
        self.started = False
        self.debug = False
        self.recent = {}  # D-Bus monitors can see the same Notify twice
        self.lock = threading.Lock()

    def add(self, source):
        self.sources.append(source)
        if not self.started:
            self.start()

    def start(self):
        import dbus
        import dbus.mainloop.glib

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        rule = "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"
        bus.call_blocking("org.freedesktop.DBus", "/org/freedesktop/DBus",
                          "org.freedesktop.DBus.Monitoring", "BecomeMonitor",
                          "asu", ([rule], dbus.UInt32(0)))
        bus.add_message_filter(self.on_message)
        self.bus = bus  # keep the connection alive
        self.started = True
        log.info("Listening for desktop notifications")

    def on_message(self, _bus, msg):
        if msg.get_member() != "Notify":
            return
        try:
            # Notify(app_name, replaces_id, app_icon, summary, body, actions, hints, timeout)
            args = msg.get_args_list()
            self.dispatch(str(args[0]), str(args[3]), str(args[4]), str(dict(args[6]).get("desktop-entry", "")))
        except Exception:
            log.exception("Failed to handle notification")

    def dispatch(self, app_name, summary, body, desktop_entry):
        with self.lock:
            now = time.monotonic()
            self.recent = {k: t for k, t in self.recent.items() if now - t < 2}
            key = (app_name, summary, body)
            if key in self.recent:
                return
            self.recent[key] = now
        matched = [s for s in self.sources if s.matches(app_name, summary, body, desktop_entry)]
        if self.debug:
            log.info("notification app=%r entry=%r summary=%r body=%r -> %s", app_name, desktop_entry,
                     summary, body[:120], [s.name for s in matched] or "no source")
        for source in matched:
            source.submit(Event(source=source.label, sender=strip_markup(summary), text=strip_markup(body)))


MONITOR = _Monitor()


@register
class DesktopSource(Source):
    type = "desktop"
    needs_glib = True

    def __init__(self, name, cfg, submit):
        super().__init__(name, cfg, submit)
        patterns = list(PRESETS.get(cfg.get("preset", ""), [])) + list(cfg.get("match", []))
        self.match = re.compile("|".join(patterns), re.IGNORECASE) if patterns else None
        exclude = cfg.get("exclude", [])
        self.exclude = re.compile("|".join(exclude), re.IGNORECASE) if exclude else None

    def check(self):
        problems = []
        if cfg_preset := self.cfg.get("preset"):
            if cfg_preset not in PRESETS:
                problems.append(f"source '{self.name}': unknown preset '{cfg_preset}' "
                                f"(known: {', '.join(PRESETS)})")
        if self.match is None:
            problems.append(f"source '{self.name}': set `preset` or `match` patterns")
        try:
            import dbus  # noqa: F401
            from gi.repository import GLib  # noqa: F401
        except ImportError:
            problems.append("desktop sources need python3-dbus and python3-gi (sudo apt install python3-dbus python3-gi)")
        return problems

    def matches(self, app_name, summary, body, desktop_entry):
        haystack = " ".join([app_name, summary, body, desktop_entry])
        if self.match is None or not self.match.search(haystack):
            return False
        return not (self.exclude and self.exclude.search(haystack))

    def start(self):
        MONITOR.add(self)
