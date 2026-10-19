"""Base class and registry for message sources (what triggers an alert)."""

import logging

SOURCES = {}


def register(cls):
    """Class decorator: make a source available under its `type` in config."""
    SOURCES[cls.type] = cls
    return cls


class Source:
    type = ""
    needs_glib = False  # True if the source needs the GLib main loop (D-Bus)

    def __init__(self, name, cfg, submit):
        """`submit(event)` hands an Event to the dispatcher. It is thread-safe and never blocks."""
        self.name = name
        self.cfg = cfg
        self.submit = submit
        self.log = logging.getLogger(f"ringbridge.source.{name}")

    @property
    def label(self):
        """Name used in the alert text, e.g. "New Teams message from ..."."""
        return self.cfg.get("label") or self.name.title()

    def check(self):
        """Return a list of human-readable problems with this source's setup (empty = OK)."""
        return []

    def start(self):
        """Start listening. Must not block: run in a thread or hook into the GLib loop."""
        raise NotImplementedError

    def stop(self):
        pass
