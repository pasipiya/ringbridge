import json
import unittest
import urllib.error
import urllib.request

from ringbridge.channels.sip import classify_close
from ringbridge.sources.desktop import MONITOR, DesktopSource
from ringbridge.sources.webhook import WebhookSource


class DesktopMatchTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.teams = DesktopSource("teams", {"preset": "teams"}, self.events.append)
        self.slack = DesktopSource("slack", {"preset": "slack", "exclude": ["#random"]}, self.events.append)

    def test_teams_pwa_in_chrome(self):
        body = '<a href="https://teams.microsoft.com/">teams.microsoft.com</a>\n\nCan you check prod?'
        self.assertTrue(self.teams.matches("Google Chrome", "John Doe", body, ""))
        self.assertFalse(self.slack.matches("Google Chrome", "John Doe", body, ""))

    def test_google_chat_is_not_teams(self):
        self.assertFalse(self.teams.matches("Google Chrome", "Jane", "chat.google.com hello", ""))

    def test_exclude(self):
        self.assertTrue(self.slack.matches("Slack", "Bob", "#incidents: db down", ""))
        self.assertFalse(self.slack.matches("Slack", "Bob", "#random: lunch?", ""))

    def test_monitor_dedupes_and_strips_markup(self):
        MONITOR.sources = [self.teams]
        MONITOR.recent = {}
        for _ in range(2):  # D-Bus monitors see the same Notify twice
            MONITOR.dispatch("Google Chrome", "<b>John</b>", "teams.microsoft.com hi", "")
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].source, "Teams")
        self.assertEqual(self.events[0].sender, "John")


class WebhookTest(unittest.TestCase):
    TOKEN = "a-very-long-test-token-123"

    def setUp(self):
        self.events = []
        self.src = WebhookSource("ci", {"listen": "127.0.0.1:0", "token": self.TOKEN}, self.events.append)
        self.src.start()
        self.base = "http://127.0.0.1:%d" % self.src.server.server_address[1]

    def tearDown(self):
        self.src.stop()

    def post(self, body, token):
        req = urllib.request.Request(self.base + "/alert", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code

    def test_accepts_valid_token(self):
        self.assertEqual(self.post({"sender": "CI", "text": "deploy failed"}, self.TOKEN), 202)
        self.assertEqual(self.events[0].alert_text(), "New Ci message from CI")

    def test_rejects_bad_token(self):
        self.assertEqual(self.post({"sender": "x"}, "wrong"), 401)
        self.assertEqual(self.events, [])

    def test_health(self):
        with urllib.request.urlopen(self.base + "/health", timeout=5) as resp:
            self.assertEqual(resp.status, 200)

    def test_rejects_placeholder_token_in_check(self):
        src = WebhookSource("w", {"token": "change-me-to-a-long-random-string"}, None)
        self.assertTrue(src.check())


class SipCloseTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_close("x: session closed: 603 Decline"), "declined")
        self.assertEqual(classify_close("x: session closed: 486 Busy Here"), "declined")
        self.assertEqual(classify_close("x: session closed: 480 Temporarily Unavailable"), "retry")
        self.assertEqual(classify_close("x: session closed: 404 Not Found"), "failed")
        self.assertEqual(classify_close("x: session closed: 403 Forbidden"), "failed")


if __name__ == "__main__":
    unittest.main()
