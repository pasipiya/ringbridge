"""The Event every source produces and every channel consumes."""

import re
from dataclasses import dataclass, field
import time


@dataclass
class Event:
    source: str          # source name from config, e.g. "teams"
    sender: str = ""     # who/what triggered it (notification title, webhook "sender")
    text: str = ""       # message body; never forwarded to a phone channel
    received: float = field(default_factory=time.time)

    def alert_text(self, include_sender=True):
        """Short, privacy-safe text for the phone: source and sender only."""
        text = f"New {self.source} message"
        if include_sender and self.sender:
            text += " from " + self.sender[:60]
        return text


def strip_markup(text):
    """Remove <script>/<style> blocks and HTML tags, as found in notifications and web replies."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text or "", flags=re.IGNORECASE | re.DOTALL)
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())
