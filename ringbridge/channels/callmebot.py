"""Telegram voice call via the free CallMeBot API (https://www.callmebot.com)."""

import urllib.error
import urllib.parse
import urllib.request

from ringbridge.channels.base import Channel, Outcome, register
from ringbridge.events import strip_markup

API = "https://api.callmebot.com/start.php"


@register
class CallMeBotChannel(Channel):
    name = "callmebot"
    required = ("username",)

    def alert(self, text, ctx):
        username = self.cfg["username"].strip()
        if not username.startswith("@"):
            username = "@" + username
        params = {
            "source": "ringbridge",
            "user": username,
            "text": text,
            "lang": self.cfg.get("lang", "en-US-Standard-B"),
            "rpt": self.cfg.get("repeat", 2),
        }
        self.log.info("Calling %s: %s", username, text)
        try:
            with urllib.request.urlopen(API + "?" + urllib.parse.urlencode(params), timeout=60) as resp:
                reply = strip_markup(resp.read().decode("utf-8", "replace"))[:1000]
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            self.log.error("Request failed: %s", e)
            return Outcome.FAILED
        low = reply.lower()
        if "not authorized" in low or "not received" in low or "error" in low:
            self.log.error("Call failed: %s", reply)
            return Outcome.FAILED
        self.log.info("Reply: %s", reply)
        return Outcome.UNACKNOWLEDGED  # CallMeBot can't tell us whether you picked up
