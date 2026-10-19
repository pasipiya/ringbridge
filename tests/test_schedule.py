import datetime as dt
import unittest

from ringbridge.schedule import in_shift

MONDAY = dt.datetime(2026, 10, 12)


def at(day, hour, minute=0):
    return MONDAY + dt.timedelta(days=day, hours=hour, minutes=minute)


class ScheduleTest(unittest.TestCase):
    def test_no_windows_is_always_on(self):
        self.assertTrue(in_shift({}))
        self.assertTrue(in_shift({"windows": []}))

    def test_day_window(self):
        s = {"windows": ["09:00-12:00"], "days": ["mon"]}
        self.assertTrue(in_shift(s, at(0, 10)))
        self.assertFalse(in_shift(s, at(0, 12)))  # end is exclusive
        self.assertFalse(in_shift(s, at(1, 10)))  # Tuesday not listed

    def test_overnight_window_belongs_to_start_day(self):
        s = {"windows": ["22:00-06:00"], "days": ["mon"]}
        self.assertTrue(in_shift(s, at(0, 23)))   # Monday night
        self.assertTrue(in_shift(s, at(1, 3)))    # Tuesday early morning, Monday's shift
        self.assertFalse(in_shift(s, at(1, 7)))
        self.assertFalse(in_shift(s, at(0, 3)))   # Monday early morning is Sunday's shift


if __name__ == "__main__":
    unittest.main()
