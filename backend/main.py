import json
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from . import db, ranking, weather, nl_search, photos, stats, itinerary, details

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
PLACES_FILE = ROOT / "data" / "places.json"
FESTIVALS_FILE = ROOT / "data" / "festivals.json"
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="India Tourism Recommender")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_curated() -> list[dict]:
    with open(PLACES_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_festivals() -> list[dict]:
    with open(FESTIVALS_FILE, encoding="utf-8") as f:
        return json.load(f)


def all_places() -> list[dict]:
    curated = load_curated()
    custom = db.get_custom_places()
    for p in custom:
        p["custom"] = True
    return curated + custom


@app.on_event("startup")
def on_startup():
    db.init_db()


@app.get("/api/places")
def list_places():
    places = all_places()
    for p in places:
        photo = db.get_cached_photo(p["id"])
        if photo:
            p["thumb_url"] = photo.get("thumb_url")
            p["image_url"] = photo.get("image_url")
    return {
        "count": len(places),
        "current_month": datetime.now().month,
        "weather_enabled": weather.get_api_key() is not None,
        "places": places,
    }


@app.get("/api/festivals")
def get_festivals(month: int | None = None, place_id: str | None = None):
    festivals = load_festivals()
    if month:
        festivals = [f for f in festivals if month in f.get("months", [])]
    if place_id:
        festivals = [f for f in festivals if place_id in f.get("place_ids", [])]
    festivals.sort(key=lambda f: min(f.get("months") or [13]))
    return {"count": len(festivals), "festivals": festivals}


@app.get("/api/photo/{place_id}")
async def get_photo(place_id: str):
    places = all_places()
    place = next((p for p in places if p["id"] == place_id), None)
    if not place:
        raise HTTPException(404, "Place not found")
    photo = await photos.fetch_photo(place)
    if not photo:
        raise HTTPException(404, "No photo found")
    return photo


@app.post("/api/photos/prefetch")
async def prefetch_photos(limit: int = 30):
    """Warm the photo cache for the first N places (by must-see score)."""
    places = all_places()
    places.sort(key=lambda p: -p.get("must_see_score", 0))
    fetched = 0
    skipped = 0
    for p in places[:limit]:
        cached = db.get_cached_photo(p["id"])
        if cached:
            skipped += 1
            continue
        r = await photos.fetch_photo(p)
        if r:
            fetched += 1
    return {"fetched": fetched, "skipped_cached": skipped}


class ItineraryRequest(BaseModel):
    start_city: str
    start_lat: float
    start_lon: float
    days: int
    month: int | None = None
    interests: list[str] = []
    exclude_ids: list[str] = []
    include_only_ids: list[str] | None = None


@app.post("/api/itinerary")
async def build_itinerary(req: ItineraryRequest):
    places = all_places()
    if req.include_only_ids is not None:
        keep = set(req.include_only_ids)
        places = [p for p in places if p["id"] in keep]
        if not places:
            return {"error": "Wishlist is empty"}
    exclude = set(req.exclude_ids)
    month = req.month or datetime.now().month
    plan = await itinerary.plan(
        places, req.start_city, req.start_lat, req.start_lon,
        req.days, month, req.interests, exclude,
    )
    return plan


class CustomPlace(BaseModel):
    id: str
    name: str
    state: str
    region: str
    city: str | None = None
    lat: float
    lon: float
    type: list[str] = []
    best_months: list[int] = []
    ideal_temp_min: float | None = None
    ideal_temp_max: float | None = None
    accessibility: int = 3
    must_see_score: int = 3
    duration_days: int = 1
    description: str = ""


@app.post("/api/places")
def add_place(place: CustomPlace):
    data = place.model_dump()
    data["custom"] = True
    db.add_custom_place(data)
    return {"ok": True, "place": data}


@app.delete("/api/places/{place_id}")
def delete_place(place_id: str):
    db.delete_custom_place(place_id)
    return {"ok": True}


class RecommendBody(BaseModel):
    top_n: int = 10
    use_weather: bool = True
    month: int | None = None
    region: str | None = None
    place_type: str | None = None
    exclude_ids: list[str] = []


@app.post("/api/recommendations")
async def recommendations(body: RecommendBody):
    exclude = set(body.exclude_ids)
    places = all_places()

    if body.region:
        places = [p for p in places if p.get("region", "").lower() == body.region.lower()]
    if body.place_type:
        places = [p for p in places if body.place_type.lower() in [t.lower() for t in p.get("type", [])]]

    initial = ranking.rank_places(places, exclude, month=body.month)
    top_candidates = initial[: min(body.top_n * 2, 30)]

    weather_lookup = {}
    if body.use_weather and weather.get_api_key():
        weather_lookup = await weather.fetch_many(top_candidates, limit=len(top_candidates))

    ranked = ranking.rank_places(
        [p for p in places if p["id"] in {c["id"] for c in top_candidates}],
        exclude,
        weather_lookup=weather_lookup,
        month=body.month,
    )
    return {
        "count": len(ranked[:body.top_n]),
        "current_month": body.month or datetime.now().month,
        "weather_used": bool(weather_lookup),
        "recommendations": ranked[:body.top_n],
    }


class SearchQuery(BaseModel):
    query: str
    use_weather: bool = False
    exclude_ids: list[str] = []


@app.post("/api/search")
async def search(body: SearchQuery):
    if not body.query.strip():
        raise HTTPException(400, "Query is empty")

    filters = await nl_search.parse_query(body.query)
    exclude = set(body.exclude_ids)
    places = all_places()

    matched = nl_search.apply_filters(places, filters, exclude)

    rank_month = (filters.get("months") or [datetime.now().month])[0]

    weather_lookup = {}
    if body.use_weather and weather.get_api_key() and matched:
        weather_lookup = await weather.fetch_many(matched, limit=min(len(matched), 20))

    ranked = ranking.rank_places(
        matched,
        exclude,
        weather_lookup=weather_lookup,
        month=rank_month,
    )

    top_n = filters.get("top_n") or 20
    return {
        "query": body.query,
        "filters": filters,
        "month_used": rank_month,
        "count": len(ranked[:top_n]),
        "total_matched": len(ranked),
        "weather_used": bool(weather_lookup),
        "results": ranked[:top_n],
    }


@app.get("/api/details/{place_id}")
async def place_details(place_id: str):
    places = all_places()
    place = next((p for p in places if p["id"] == place_id), None)
    if not place:
        raise HTTPException(404, "Place not found")
    d = await details.fetch_details(place)
    if not d:
        raise HTTPException(503, "Could not generate details (LLM unavailable)")
    return d


@app.get("/api/weather/{place_id}")
async def place_weather(place_id: str):
    places = all_places()
    place = next((p for p in places if p["id"] == place_id), None)
    if not place:
        raise HTTPException(404, "Place not found")
    w = await weather.fetch_weather(place["lat"], place["lon"], place_id)
    if not w:
        raise HTTPException(503, "Weather unavailable (missing API key or fetch failed)")
    return w


# Serve frontend
DATA_DIR = ROOT / "data"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")
