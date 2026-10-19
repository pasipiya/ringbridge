"""Base class and registry for phone alert channels."""

import enum
import logging

CHANNELS = {}


def register(cls):
    """Class decorator: make a channel available under its `name` in config."""
    CHANNELS[cls.name] = cls
    return cls


class Outcome(enum.Enum):
    ACKNOWLEDGED = "acknowledged"      # you answered / declined / tapped / came back to the laptop
    UNACKNOWLEDGED = "unacknowledged"  # delivered, but no reaction before giving up
    FAILED = "failed"                  # could not deliver; the next channel in the chain is tried


class Channel:
    name = ""
    required = ()  # config keys that must be non-empty

    def __init__(self, cfg):
        self.cfg = cfg
        self.log = logging.getLogger(f"ringbridge.channel.{self.name}")

    def check(self):
        """Return a list of human-readable problems with this channel's setup (empty = OK)."""
        return [f"[channels.{self.name}] '{key}' is not set" for key in self.required if not self.cfg.get(key)]

    def alert(self, text, ctx):
        """Alert the phone until acknowledged or given up. Returns an Outcome."""
        raise NotImplementedError
