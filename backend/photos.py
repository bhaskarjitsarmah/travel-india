"""Wikipedia-based photo fetcher with SQLite cache."""
import httpx
from urllib.parse import quote

from . import db

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


# Manual overrides where the place name doesn't match a Wikipedia page well.
TITLE_OVERRIDES = {
    "goa-north": "North_Goa",
    "goa-south": "South_Goa",
    "dudhsagar": "Dudhsagar_Falls",
    "valley-of-flowers": "Valley_of_Flowers_National_Park",
    "leh-ladakh": "Leh",
    "pangong-tso": "Pangong_Tso",
    "tso-moriri": "Tso_Moriri",
    "nubra-valley": "Nubra_Valley",
    "rann-of-kutch": "Rann_of_Kutch",
    "statue-of-unity": "Statue_of_Unity",
    "jim-corbett": "Jim_Corbett_National_Park",
    "ranthambore": "Ranthambore_National_Park",
    "kanha": "Kanha_Tiger_Reserve",
    "bandhavgarh": "Bandhavgarh_National_Park",
    "pench": "Pench_Tiger_Reserve",
    "tadoba": "Tadoba_Andhari_Tiger_Reserve",
    "kaziranga": "Kaziranga_National_Park",
    "gir": "Gir_National_Park",
    "bandipur": "Bandipur_National_Park",
    "thekkady": "Periyar_National_Park",
    "sundarbans": "Sundarbans_National_Park",
    "majuli": "Majuli",
    "loktak": "Loktak_Lake",
    "chilika": "Chilika_Lake",
    "havelock": "Swaraj_Dweep",
    "neil-island": "Shaheed_Dweep",
    "port-blair": "Port_Blair",
    "lakshadweep": "Lakshadweep",
    "alleppey": "Alappuzha",
    "amritsar": "Golden_Temple",
    "varanasi": "Varanasi",
    "delhi": "Old_Delhi",
    "mahabalipuram": "Mahabalipuram",
    "kanyakumari": "Kanyakumari",
    "dharamshala": "McLeod_Ganj",
    "rishikesh": "Rishikesh",
    "kasol": "Kasol",
    "bir-billing": "Bir,_Himachal_Pradesh",
    "chopta": "Chopta",
    "auli": "Auli",
    "tsomgo": "Tsongmo_Lake",
    "dzukou": "Dzükou_Valley",
    "living-root-bridges": "Living_root_bridge",
    "mathura-vrindavan": "Vrindavan",
    "araku-valley": "Araku_Valley",
    "badami": "Badami_cave_temples",
    "mawlynnong": "Mawlynnong",
    "thanjavur": "Thanjavur",
    "konark": "Konark_Sun_Temple",
    "bodh-gaya": "Mahabodhi_Temple",
    "nalanda": "Nalanda_mahavihara",
    "vaishno-devi": "Vaishno_Devi_Temple",
    "tirupati": "Tirumala_Venkateswara_Temple",
    "shirdi": "Shirdi_Sai_Baba_Temple",
    "ziro-valley": "Ziro",
    "pushkar": "Pushkar",
    "mount-abu": "Mount_Abu",
}


def _title_for(place: dict) -> str:
    pid = place["id"]
    if pid in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[pid]
    name = place["name"]
    # Strip parenthetical sub-names: "Goa (North)" -> "Goa"
    name = name.split("(")[0].strip()
    return name.replace(" ", "_")


async def fetch_photo(place: dict) -> dict | None:
    pid = place["id"]
    cached = db.get_cached_photo(pid)
    if cached and (cached.get("thumb_url") or cached.get("image_url")):
        return cached
    if cached and cached.get("source") == "miss":
        # We previously failed; don't hammer Wikipedia
        return None

    title = _title_for(place)
    url = WIKI_SUMMARY.format(title=quote(title))
    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            headers={"User-Agent": "IndiaTourismApp/1.0 (personal use)"},
        ) as client:
            r = await client.get(url, follow_redirects=True)
            if r.status_code != 200:
                db.cache_photo(pid, None, None, "miss")
                return None
            data = r.json()
            thumb = (data.get("thumbnail") or {}).get("source")
            full = (data.get("originalimage") or {}).get("source")
            if not thumb and not full:
                db.cache_photo(pid, None, None, "miss")
                return None
            db.cache_photo(pid, full, thumb, "wikipedia")
            return {"image_url": full, "thumb_url": thumb, "source": "wikipedia"}
    except Exception:
        return None
