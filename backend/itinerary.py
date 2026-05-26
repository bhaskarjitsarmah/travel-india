"""LLM-driven itinerary builder. Feeds the LLM a compact view of candidate places
and asks for a structured day-by-day plan."""
import os
import json
import re
import httpx
from math import radians, sin, cos, asin, sqrt

SYSTEM_PROMPT = """You are an experienced India trip planner. Build a feasible day-by-day itinerary from the given candidates.

RULES:
- Cluster nearby places — minimize back-and-forth.
- Generally 1–2 days per place; allow 0.5 day if it's a quick stop.
- Include explicit travel days (or partial-day transit notes) between distant clusters.
- Respect the trip month — avoid Ladakh/Spiti in winter, monsoon-closed parks in Jul/Aug, etc.
- Use only the place IDs from the CANDIDATES list. Never invent IDs.
- Stay within the requested total number of days.
- Start the itinerary from the user's starting city.

Output ONLY valid JSON, no prose or markdown fences:
{
  "summary": "Short paragraph describing the trip arc",
  "total_days": 7,
  "estimated_distance_km": 1500,
  "days": [
    {"day": 1, "place_id": "jaipur", "title": "Arrive Jaipur", "notes": "City Palace + Hawa Mahal in afternoon", "travel": null},
    {"day": 2, "place_id": "jaipur", "title": "Amber Fort + Old City", "notes": "Sunrise at Amber, evening at Jaigarh", "travel": null},
    {"day": 3, "place_id": "pushkar", "title": "Drive to Pushkar (3h)", "notes": "Holy lake, sunset at Savitri Temple", "travel": "Jaipur → Pushkar, ~150km / 3h by road"}
  ]
}"""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


def _build_candidate_list(
    places: list[dict],
    start_lat: float,
    start_lon: float,
    month: int,
    max_candidates: int = 50,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    exclude_ids = exclude_ids or set()
    pool = []
    for p in places:
        if p["id"] in exclude_ids:
            continue
        season_ok = month in (p.get("best_months") or list(range(1, 13)))
        dist = _haversine(start_lat, start_lon, p["lat"], p["lon"])
        score = (1.0 if season_ok else 0.4) * (p.get("must_see_score", 3) / 5) / max(1.0, dist / 800)
        pool.append((score, dist, p))
    pool.sort(key=lambda x: -x[0])
    out = []
    for _, dist, p in pool[:max_candidates]:
        out.append({
            "id": p["id"],
            "name": p["name"],
            "state": p["state"],
            "region": p["region"],
            "lat": p["lat"],
            "lon": p["lon"],
            "type": p.get("type", []),
            "best_months": p.get("best_months", []),
            "must_see": p.get("must_see_score", 3),
            "duration_days": p.get("duration_days", 2),
            "distance_from_start_km": round(dist),
        })
    return out


async def plan(
    places: list[dict],
    start_city: str,
    start_lat: float,
    start_lon: float,
    days: int,
    month: int,
    interests: list[str] | None = None,
    exclude_ids: set[str] | None = None,
) -> dict:
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not base_url or not api_key:
        return {"error": "LLM not configured"}

    candidates = _build_candidate_list(
        places, start_lat, start_lon, month,
        max_candidates=min(60, len(places)),
        exclude_ids=exclude_ids,
    )

    user_msg = json.dumps({
        "start_city": start_city,
        "start_lat": start_lat,
        "start_lon": start_lon,
        "trip_days": days,
        "trip_month": month,
        "interests": interests or [],
        "candidates": candidates,
    })

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                return {"error": f"LLM error HTTP {r.status_code}: {r.text[:200]}"}
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            return json.loads(_strip_fences(text))
    except Exception as e:
        return {"error": f"LLM exception: {e}"}
