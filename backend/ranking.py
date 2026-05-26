from datetime import datetime


DEFAULT_WEIGHTS = {
    "season": 0.35,
    "must_see": 0.30,
    "access": 0.15,
    "weather": 0.20,
}


def _season_score(place: dict, month: int) -> float:
    best = place.get("best_months", [])
    if not best:
        return 0.5
    if month in best:
        return 1.0
    prev_m = 12 if month == 1 else month - 1
    next_m = 1 if month == 12 else month + 1
    if prev_m in best or next_m in best:
        return 0.55
    return 0.15


def _weather_score(place: dict, weather: dict | None) -> float | None:
    if not weather or "temp" not in weather:
        return None
    t = weather["temp"]
    tmin = place.get("ideal_temp_min")
    tmax = place.get("ideal_temp_max")
    if tmin is None or tmax is None:
        return None
    if tmin <= t <= tmax:
        base = 1.0
    else:
        diff = min(abs(t - tmin), abs(t - tmax))
        base = max(0.0, 1.0 - diff / 18.0)
    cond = (weather.get("main") or "").lower()
    bad = {"thunderstorm": 0.65, "snow": 0.85, "rain": 0.8, "drizzle": 0.9}
    if cond in bad:
        base *= bad[cond]
    return round(base, 3)


def score_place(place: dict, month: int, weather: dict | None = None,
                weights: dict = None) -> dict:
    w = weights or DEFAULT_WEIGHTS
    season = _season_score(place, month)
    must = place.get("must_see_score", 3) / 5.0
    access = place.get("accessibility", 3) / 5.0
    weather_s = _weather_score(place, weather)

    if weather_s is None:
        # redistribute weather weight onto season
        total = (w["season"] + w["weather"]) * season \
                + w["must_see"] * must \
                + w["access"] * access
    else:
        total = (w["season"] * season
                 + w["must_see"] * must
                 + w["access"] * access
                 + w["weather"] * weather_s)

    return {
        "score": round(total, 3),
        "season": round(season, 3),
        "must_see": round(must, 3),
        "access": round(access, 3),
        "weather": weather_s,
    }


def rank_places(places: list[dict], visited_ids: set[str],
                weather_lookup: dict[str, dict] | None = None,
                include_visited: bool = False,
                month: int | None = None) -> list[dict]:
    month = month or datetime.now().month
    weather_lookup = weather_lookup or {}
    out = []
    for p in places:
        if not include_visited and p["id"] in visited_ids:
            continue
        weather = weather_lookup.get(p["id"])
        s = score_place(p, month, weather)
        out.append({**p, "scoring": s, "visited": p["id"] in visited_ids})
    out.sort(key=lambda x: x["scoring"]["score"], reverse=True)
    return out
