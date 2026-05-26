import os
import time
import httpx

API_URL = "https://api.openweathermap.org/data/2.5/weather"
_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 1800  # 30 minutes


def get_api_key() -> str | None:
    return os.getenv("OPENWEATHER_API_KEY")


async def fetch_weather(lat: float, lon: float, place_id: str) -> dict | None:
    key = get_api_key()
    if not key:
        return None

    cached = _CACHE.get(place_id)
    if cached and (time.time() - cached[0]) < CACHE_TTL:
        return cached[1]

    params = {"lat": lat, "lon": lon, "appid": key, "units": "metric"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(API_URL, params=params)
            if r.status_code != 200:
                return None
            data = r.json()
            result = {
                "temp": data["main"]["temp"],
                "feels_like": data["main"]["feels_like"],
                "humidity": data["main"]["humidity"],
                "main": data["weather"][0]["main"],
                "description": data["weather"][0]["description"],
                "wind_speed": data.get("wind", {}).get("speed"),
            }
            _CACHE[place_id] = (time.time(), result)
            return result
    except Exception:
        return None


async def fetch_many(places: list[dict], limit: int = 30) -> dict[str, dict]:
    """Fetch weather for the first `limit` places to bound API usage."""
    import asyncio
    key = get_api_key()
    if not key:
        return {}
    subset = places[:limit]
    coros = [fetch_weather(p["lat"], p["lon"], p["id"]) for p in subset]
    results = await asyncio.gather(*coros)
    return {p["id"]: r for p, r in zip(subset, results) if r is not None}
