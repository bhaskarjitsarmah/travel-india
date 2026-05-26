"""LLM-generated rich travel details for each place, cached in SQLite."""
import os
import json
import re
import httpx

from . import db

SYSTEM_PROMPT = """You are an experienced India travel guide. Produce concise, useful tourist information about a specific Indian destination.

Output ONLY valid JSON in this exact schema:
{
  "interesting_facts": ["3-5 short, specific, fascinating facts (history, architecture, records, geography, culture)"],
  "must_do": ["4-6 essential experiences. Each item must be specific and actionable, not generic."],
  "do_tips": ["3-5 useful practical do tips (timing, dress code, photography, etiquette)"],
  "dont_tips": ["3-5 things to AVOID (scams, cultural insensitivity, safety, restricted activities)"],
  "best_time_of_day": "One sentence on best time of day to visit and why",
  "local_food": ["3-4 specific local dishes or food experiences (with dish names)"],
  "getting_there": "1-2 sentences on how to reach (nearest airport/station, road, key gateways)",
  "approx_budget_inr": "Rough daily per-person budget in INR for a mid-range traveler, with one short note"
}

Be concrete. No filler. No marketing language. Output the JSON only, no markdown fences."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def fetch_details(place: dict) -> dict | None:
    pid = place["id"]
    cached = db.get_cached_details(pid)
    if cached:
        return cached

    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not base_url or not api_key:
        return None

    user_msg = (
        f"Place: {place['name']}\n"
        f"State: {place['state']}\n"
        f"Region: {place['region']}\n"
        f"Types: {', '.join(place.get('type', []))}\n"
        f"Short description: {place.get('description', '')}"
    )

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 1200,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                return None
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            parsed = json.loads(_strip_fences(text))
            db.cache_details(pid, parsed)
            return parsed
    except Exception:
        return None
