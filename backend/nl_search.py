import os
import json
import re
import httpx

SYSTEM_PROMPT = """You are a query parser for an Indian tourism app. Convert the user's natural-language query into a strict JSON filter object.

The dataset has these enumerated values:
- regions: ["North", "South", "East", "West", "Central", "Northeast", "Islands"]
- types: ["hills", "beach", "heritage", "spiritual", "wildlife", "nature", "adventure", "city", "lake", "desert", "island", "remote", "iconic"]
- months: integers 1..12 (Jan..Dec)
- accessibility: 1..5 (5 = very easy to reach, 1 = remote)
- must_see_score: 1..5 (5 = world-famous must-see)

Map user phrasings to these values. Examples:
- "scenic" / "nature" / "beautiful" / "picturesque" -> types: ["nature","hills","lake"]
- "easy to reach" / "high accessibility" / "well connected" -> min_accessibility: 4
- "offbeat" / "remote" / "hidden gem" / "less crowded" -> max_accessibility: 3
- "must-see" / "world famous" / "iconic" -> min_must_see: 5
- "north India" -> regions: ["North"]
- "north east" / "northeast" -> regions: ["Northeast"]
- "south India" -> regions: ["South"]
- "in July" -> months: [7]
- "summer" -> months: [4,5,6]
- "monsoon" -> months: [7,8,9]
- "winter" -> months: [12,1,2]
- "spring" -> months: [3,4]
- "for trekking" -> types: ["adventure","hills"]
- "for couples" / "romantic" -> types: ["beach","hills","heritage"]; keywords:["romantic"]
- "spiritual" / "pilgrimage" / "temple" -> types: ["spiritual"]
- "wildlife" / "tiger" / "safari" -> types: ["wildlife"]
- "beach" / "coast" / "sea" -> types: ["beach"]
- specific state names -> states: ["Kerala", ...]

Output ONLY valid JSON in this exact schema (omit keys you can't infer):
{
  "regions": ["North"],
  "states": [],
  "types": ["nature","hills"],
  "months": [7],
  "min_accessibility": 4,
  "max_accessibility": null,
  "min_must_see": null,
  "keywords": ["scenic"],
  "include_visited": false,
  "top_n": 10
}

Return ONLY the JSON object. No prose, no markdown fences."""


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def parse_query(query: str) -> dict:
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not base_url or not api_key:
        return _fallback_parse(query)

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        "temperature": 0.0,
        "max_tokens": 400,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                return {**_fallback_parse(query), "_llm_error": f"HTTP {r.status_code}: {r.text[:200]}"}
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            parsed = json.loads(_strip_fences(text))
            parsed["_source"] = "llm"
            return parsed
    except Exception as e:
        return {**_fallback_parse(query), "_llm_error": str(e)}


def _fallback_parse(query: str) -> dict:
    """Regex fallback if LLM is unavailable. Limited but works offline."""
    q = query.lower()
    out: dict = {"_source": "fallback"}

    regions = []
    for r, keys in {
        "North": ["north india", "northern india", " north "],
        "South": ["south india", "southern india", " south "],
        "East": [" east india", " eastern india"],
        "West": [" west india", " western india"],
        "Central": ["central india"],
        "Northeast": ["north east", "northeast", "north-east"],
        "Islands": ["andaman", "lakshadweep", "island"],
    }.items():
        if any(k in f" {q} " for k in keys):
            regions.append(r)
    if regions:
        out["regions"] = regions

    months = []
    month_names = ["january","february","march","april","may","june",
                   "july","august","september","october","november","december"]
    for i, name in enumerate(month_names, 1):
        if name in q or name[:3] in q.split():
            months.append(i)
    if "summer" in q: months += [4,5,6]
    if "monsoon" in q or "rain" in q: months += [7,8,9]
    if "winter" in q: months += [12,1,2]
    if "spring" in q: months += [3,4]
    if months:
        out["months"] = sorted(set(months))

    types = []
    type_map = {
        "hills": ["hill","mountain","trek"],
        "beach": ["beach","coast","sea"],
        "heritage": ["heritage","fort","palace","historical"],
        "spiritual": ["spiritual","temple","pilgrim","religious"],
        "wildlife": ["wildlife","tiger","safari","national park"],
        "nature": ["nature","scenic","picturesque","beautiful"],
        "adventure": ["adventure","trekking","rafting","paraglid"],
        "lake": ["lake"],
        "desert": ["desert"],
        "island": ["island"],
    }
    for t, keys in type_map.items():
        if any(k in q for k in keys):
            types.append(t)
    if types:
        out["types"] = types

    if any(p in q for p in ["easy to reach", "accessible", "well connected", "high accessibility"]):
        out["min_accessibility"] = 4
    if any(p in q for p in ["offbeat", "remote", "hidden", "less crowded"]):
        out["max_accessibility"] = 3
    if any(p in q for p in ["must see", "must-see", "iconic", "world famous", "famous"]):
        out["min_must_see"] = 4

    return out


def apply_filters(places: list[dict], filters: dict, visited_ids: set[str]) -> list[dict]:
    out = []
    regions = set(filters.get("regions") or [])
    states = set((filters.get("states") or []))
    types_f = set(t.lower() for t in (filters.get("types") or []))
    months = set(filters.get("months") or [])
    min_acc = filters.get("min_accessibility")
    max_acc = filters.get("max_accessibility")
    min_must = filters.get("min_must_see")
    keywords = [k.lower() for k in (filters.get("keywords") or [])]
    include_visited = filters.get("include_visited", False)

    for p in places:
        if not include_visited and p["id"] in visited_ids:
            continue
        if regions and p.get("region") not in regions:
            continue
        if states and p.get("state") not in states:
            continue
        if types_f and not (set(t.lower() for t in p.get("type", [])) & types_f):
            continue
        if months and not (set(p.get("best_months", [])) & months):
            continue
        if min_acc is not None and p.get("accessibility", 0) < min_acc:
            continue
        if max_acc is not None and p.get("accessibility", 999) > max_acc:
            continue
        if min_must is not None and p.get("must_see_score", 0) < min_must:
            continue
        out.append(p)

    # If keyword filter was given, use it as a SOFT boost only when results exist.
    # Places matching a keyword bubble to the top; non-matches still included.
    if keywords and out:
        def kw_score(p):
            blob = (p.get("name", "") + " " + p.get("description", "") + " "
                    + " ".join(p.get("type", []))).lower()
            return sum(1 for k in keywords if k in blob)
        out.sort(key=kw_score, reverse=True)
    return out
