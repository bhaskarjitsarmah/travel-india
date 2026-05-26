"""Detect upcoming long weekends from Indian holidays.

Uses the `holidays` library for algorithmic generation — no static JSON,
no annual manual updates. Lunar/Islamic holidays are marked '(estimated)'
by the library; we surface that as the 'approximate' flag.
"""
import re
from datetime import date, timedelta
import holidays as _holidays

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_ESTIMATED_RE = re.compile(r"\s*\(estimated\)\s*$", re.IGNORECASE)


def _classify(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["republic day", "independence day", "gandhi", "labour", "new year"]):
        return "national"
    if any(k in n for k in ["christmas", "good friday", "easter"]):
        return "religious"
    if any(k in n for k in ["diwali", "holi", "dussehra", "janmashtami", "ganesh", "shivaratri",
                              "ram navami", "mahavir", "guru nanak", "buddha", "onam", "pongal",
                              "rath yatra", "navaratri", "raksha"]):
        return "religious"
    if any(k in n for k in ["eid", "bakrid", "id-ul", "muharram", "milad", "ramzan"]):
        return "religious"
    return "regional"


def _build_holidays_for_range(start: date, end: date) -> list[dict]:
    years = list(range(start.year, end.year + 2))
    ind = _holidays.country_holidays("IN", years=years)
    out = []
    for d, name in ind.items():
        if d < start or d > end:
            continue
        approximate = bool(_ESTIMATED_RE.search(name))
        clean_name = _ESTIMATED_RE.sub("", name).strip()
        out.append({
            "date": d.isoformat(),
            "name": clean_name,
            "type": _classify(clean_name),
            "approximate": approximate,
        })
    out.sort(key=lambda x: x["date"])
    return out


def _parse(d: str) -> date:
    from datetime import datetime as _dt
    return _dt.strptime(d, "%Y-%m-%d").date()


def find_long_weekends(today: date | None = None, lookahead_days: int = 400) -> list[dict]:
    today = today or date.today()
    end = today + timedelta(days=lookahead_days)
    holidays_list = _build_holidays_for_range(today, end + timedelta(days=7))
    holiday_map = {_parse(h["date"]): h for h in holidays_list}

    def is_off(d: date) -> bool:
        return d.weekday() in (5, 6) or d in holiday_map

    seen: set[date] = set()
    results = []
    d = today
    while d <= end:
        if d in seen or not is_off(d):
            d += timedelta(days=1)
            continue
        start = d
        while is_off(start - timedelta(days=1)) and start > today - timedelta(days=7):
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

        if length >= 3 and stretch_holidays and stop >= today:
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
