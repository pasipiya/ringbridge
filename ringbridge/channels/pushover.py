"""Pushover emergency-priority alert: long sound, repeats until acknowledged, iOS Critical Alerts."""

import json
import urllib.error
import urllib.parse
import urllib.request

from ringbridge.channels.base import Channel, Outcome, register

API = "https://api.pushover.net/1"
NET_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError)


@register
class PushoverChannel(Channel):
    name = "pushover"
    required = ("user_key", "app_token")

    def request(self, path, fields=None):
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        with urllib.request.urlopen(API + path, data=data, timeout=30) as resp:
            return json.loads(resp.read())

    def alert(self, text, ctx):
        token = self.cfg["app_token"]
        self.log.info("Emergency alert: %s", text)
        try:
            receipt = self.request("/messages.json", {
                "token": token,
                "user": self.cfg["user_key"],
                "title": self.cfg.get("title", "ringbridge alert"),
                "message": text,
                "priority": 2,
                "retry": max(30, self.cfg.get("retry_seconds", 30)),
                "expire": min(10800, self.cfg.get("expire_seconds", 600)),
                "sound": self.cfg.get("sound", "alien"),
            })["receipt"]
        except (*NET_ERRORS, ValueError, KeyError) as e:
            detail = e.read().decode(errors="replace") if isinstance(e, urllib.error.HTTPError) else e
            self.log.error("Request failed: %s", detail)
            return Outcome.FAILED

        while True:
            if ctx.wait(5):
                self.log.info("Acknowledged (laptop activity), cancelling")
                try:
                    self.request(f"/receipts/{receipt}/cancel.json", {"token": token})
                except (*NET_ERRORS, ValueError) as e:
                    self.log.error("Cancel failed: %s", e)
                return Outcome.ACKNOWLEDGED
            try:
                status = self.request(f"/receipts/{receipt}.json?token={token}")
            except (*NET_ERRORS, ValueError) as e:
                self.log.warning("Could not check receipt: %s", e)
                continue
            if status.get("acknowledged"):
                self.log.info("Acknowledged on phone")
                return Outcome.ACKNOWLEDGED
            if status.get("expired"):
                return Outcome.UNACKNOWLEDGED
