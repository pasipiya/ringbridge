"""Push notification via ntfy (https://ntfy.sh), re-sent until acknowledged."""

import json
import urllib.error
import urllib.request

from ringbridge.channels.base import Channel, Outcome, register

NET_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError)


@register
class NtfyChannel(Channel):
    name = "ntfy"
    required = ("topic",)

    def url(self, suffix=""):
        return self.cfg.get("server", "https://ntfy.sh").rstrip("/") + "/" + self.cfg["topic"] + suffix

    def alert(self, text, ctx):
        max_alerts = self.cfg.get("max_alerts", 10)
        delivered = 0
        for n in range(1, max_alerts + 1):
            delivered += self.push(text, n, max_alerts)
            if n == max_alerts:
                break
            if self.wait_for_ack(ctx, self.cfg.get("repeat_seconds", 30)):
                return Outcome.ACKNOWLEDGED
            if not delivered and n >= 2:
                return Outcome.FAILED  # ntfy unreachable: let the next channel try
        return Outcome.UNACKNOWLEDGED if delivered else Outcome.FAILED

    def wait_for_ack(self, ctx, seconds):
        step = 5
        for _ in range(max(1, int(seconds // step))):
            if ctx.wait(step):
                self.log.info("Acknowledged (laptop activity)")
                return True
            if self.button_pressed(ctx.start):
                self.log.info("Acknowledged (I'm on it button)")
                return True
        return False

    def button_pressed(self, since):
        try:
            url = self.url("-ack") + "/json?poll=1&since=" + str(int(since))
            with urllib.request.urlopen(url, timeout=10) as resp:
                return any(json.loads(l).get("event") == "message"
                           for l in resp.read().decode().splitlines() if l.strip())
        except (*NET_ERRORS, ValueError) as e:
            self.log.warning("Could not check ack topic: %s", e)
            return False

    def push(self, text, n, total):
        req = urllib.request.Request(self.url(), data=text.encode(), method="POST", headers={
            "Title": f"{self.cfg.get('title', 'ringbridge alert')} {n}/{total}",
            "Priority": str(self.cfg.get("priority", 5)),
            "Tags": "rotating_light",
            "Actions": f"http, I'm on it, {self.url('-ack')}, method=POST, body=ack, clear=true",
        })
        self.log.info("Push %d/%d: %s", n, total, text)
        try:
            with urllib.request.urlopen(req, timeout=30):
                return True
        except NET_ERRORS as e:
            self.log.error("Push failed: %s", e)
            return False
