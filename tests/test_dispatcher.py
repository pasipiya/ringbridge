import threading
import time
import unittest

from ringbridge import dispatcher as dispatcher_mod
from ringbridge.channels import CHANNELS, Channel, Outcome
from ringbridge.dispatcher import Dispatcher
from ringbridge.events import Event

dispatcher_mod.local_warning = lambda text: None  # don't pop up desktop notifications during tests


class FakeChannel(Channel):
    calls = []

    def alert(self, text, ctx):
        FakeChannel.calls.append((self.cfg["id"], text))
        return Outcome(self.cfg["outcome"])


def make(outcomes, **alert):
    CHANNELS["fake"] = FakeChannel
    names = [f"fake{i}" for i in range(len(outcomes))]
    for n in names:
        CHANNELS[n] = FakeChannel
    cfg = {
        "schedule": {},
        "alert": {"channels": names, "ack_on_laptop_activity": False, **alert},
        "channels": {n: {"id": n, "outcome": o.value} for n, o in zip(names, outcomes)},
    }
    FakeChannel.calls = []
    return Dispatcher(cfg)


def wait_idle(d):
    for _ in range(100):
        if not d.busy:
            return
        time.sleep(0.01)


class DispatcherTest(unittest.TestCase):
    def test_falls_back_on_failure(self):
        d = make([Outcome.FAILED, Outcome.ACKNOWLEDGED, Outcome.ACKNOWLEDGED])
        self.assertIs(d.alert("x"), Outcome.ACKNOWLEDGED)
        self.assertEqual([c[0] for c in FakeChannel.calls], ["fake0", "fake1"])

    def test_unacknowledged_stops_without_escalation(self):
        d = make([Outcome.UNACKNOWLEDGED, Outcome.ACKNOWLEDGED])
        self.assertIs(d.alert("x"), Outcome.UNACKNOWLEDGED)
        self.assertEqual(len(FakeChannel.calls), 1)

    def test_unacknowledged_escalates_when_enabled(self):
        d = make([Outcome.UNACKNOWLEDGED, Outcome.ACKNOWLEDGED], escalate_unacknowledged=True)
        self.assertIs(d.alert("x"), Outcome.ACKNOWLEDGED)
        self.assertEqual(len(FakeChannel.calls), 2)

    def test_all_failed(self):
        d = make([Outcome.FAILED, Outcome.FAILED])
        self.assertIs(d.alert("x"), Outcome.FAILED)

    def test_crashing_channel_counts_as_failed(self):
        d = make([Outcome.ACKNOWLEDGED, Outcome.ACKNOWLEDGED])
        d.chain[0].alert = lambda text, ctx: 1 / 0
        self.assertIs(d.alert("x"), Outcome.ACKNOWLEDGED)

    def test_submit_cooldown_and_alert_text(self):
        d = make([Outcome.ACKNOWLEDGED], cooldown_seconds=60)
        self.assertTrue(d.submit(Event("Teams", sender="Alice", text="secret body")))
        wait_idle(d)
        self.assertFalse(d.submit(Event("Teams", sender="Bob")))  # inside cooldown
        self.assertEqual(FakeChannel.calls, [("fake0", "New Teams message from Alice")])

    def test_submit_while_busy_is_ignored(self):
        d = make([Outcome.ACKNOWLEDGED], cooldown_seconds=0)
        gate = threading.Event()
        d.chain[0].alert = lambda text, ctx: gate.wait(2) and Outcome.ACKNOWLEDGED
        self.assertTrue(d.submit(Event("Teams")))
        self.assertFalse(d.submit(Event("Teams")))
        gate.set()
        wait_idle(d)
        self.assertTrue(d.submit(Event("Teams")))

    def test_outside_shift_is_ignored(self):
        d = make([Outcome.ACKNOWLEDGED])
        d.cfg["schedule"] = {"windows": ["00:00-00:01"], "days": []}
        self.assertFalse(d.submit(Event("Teams")))


if __name__ == "__main__":
    unittest.main()
