"""Detect upcoming long weekends from the Indian holiday calendar."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

HOLIDAYS_FILE = Path(__file__).resolve().parent.parent / "data" / "holidays.json"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _load_holidays() -> list[dict]:
    with open(HOLIDAYS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def find_long_weekends(today: date | None = None, lookahead_days: int = 400) -> list[dict]:
    today = today or date.today()
    holidays = _load_holidays()
    holiday_map = {_parse(h["date"]): h for h in holidays}

    def is_off(d: date) -> bool:
        return d.weekday() in (5, 6) or d in holiday_map

    end = today + timedelta(days=lookahead_days)
    seen: set[date] = set()
    results = []
    d = today
    while d <= end:
        if d in seen or not is_off(d):
            d += timedelta(days=1)
            continue
        # Find full off-day stretch around d
        start = d
        while is_off(start - timedelta(days=1)):
            start -= timedelta(days=1)
        stop = d
        while is_off(stop + timedelta(days=1)):
            stop += timedelta(days=1)
        length = (stop - start).days + 1

        cur = start
        stretch_holidays = []
        while cur <= stop:
            if cur in holiday_map:
                stretch_holidays.append({**holiday_map[cur], "day_of_week": DAYS[cur.weekday()]})
            seen.add(cur)
            cur += timedelta(days=1)

        # Only include if length >= 3 days AND at least one holiday (not pure Sat/Sun)
        # AND stretch contains today or later
        if length >= 3 and stretch_holidays and stop >= today:
            # Skip weekends with no real long-weekend value (e.g., past)
            results.append({
                "start": start.isoformat(),
                "end": stop.isoformat(),
                "days": length,
                "start_day": DAYS[start.weekday()],
                "end_day": DAYS[stop.weekday()],
                "holidays": stretch_holidays,
                "months": sorted(set([start.month, stop.month])),
            })
        d = stop + timedelta(days=1)

    return results


def upcoming_long_weekends(limit: int = 6) -> list[dict]:
    return find_long_weekends()[:limit]
