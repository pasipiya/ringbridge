"""Shift windows: only alert during configured hours."""

import datetime as dt

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_window(text):
    start, end = (dt.time.fromisoformat(t.strip()) for t in text.split("-"))
    return start, end


def in_shift(schedule, now=None):
    """True if `now` is inside a window. No windows configured = always on.

    Overnight windows ("22:00-06:00") belong to the day they start on.
    """
    windows = [parse_window(w) for w in schedule.get("windows", [])]
    if not windows:
        return True
    days = [d.lower()[:3] for d in schedule.get("days", DAYS)]
    now = now or dt.datetime.now()
    today = DAYS[now.weekday()]
    yesterday = DAYS[(now.weekday() - 1) % 7]
    t = now.time()
    for start, end in windows:
        if start <= end:
            if today in days and start <= t < end:
                return True
        else:
            if today in days and t >= start:
                return True
            if yesterday in days and t < end:
                return True
    return False
