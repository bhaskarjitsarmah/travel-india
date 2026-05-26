from collections import Counter, defaultdict


def compute(places: list[dict], visited_ids: set[str], wishlist_ids: set[str]) -> dict:
    total = len(places)
    visited = [p for p in places if p["id"] in visited_ids]

    states_visited = {p["state"] for p in visited}
    states_total = {p["state"] for p in places}

    regions_total = Counter(p["region"] for p in places)
    regions_visited = Counter(p["region"] for p in visited)

    type_total: Counter[str] = Counter()
    type_visited: Counter[str] = Counter()
    for p in places:
        for t in p.get("type", []):
            type_total[t] += 1
            if p["id"] in visited_ids:
                type_visited[t] += 1

    must_see_visited = sum(1 for p in visited if p.get("must_see_score", 0) >= 5)
    must_see_total = sum(1 for p in places if p.get("must_see_score", 0) >= 5)

    # State-level coverage list
    state_breakdown = defaultdict(lambda: {"visited": 0, "total": 0})
    for p in places:
        state_breakdown[p["state"]]["total"] += 1
        if p["id"] in visited_ids:
            state_breakdown[p["state"]]["visited"] += 1

    state_list = sorted(
        [
            {"state": s, **v, "percentage": round(v["visited"] / v["total"] * 100) if v["total"] else 0}
            for s, v in state_breakdown.items()
        ],
        key=lambda x: (-x["visited"], x["state"]),
    )

    return {
        "visited_count": len(visited),
        "total_count": total,
        "percentage": round(len(visited) / total * 100, 1) if total else 0,
        "wishlist_count": len(wishlist_ids),
        "states_visited": sorted(states_visited),
        "states_visited_count": len(states_visited),
        "states_total_count": len(states_total),
        "regions": [
            {
                "region": r,
                "visited": regions_visited.get(r, 0),
                "total": regions_total[r],
                "percentage": round(regions_visited.get(r, 0) / regions_total[r] * 100) if regions_total[r] else 0,
            }
            for r in sorted(regions_total.keys())
        ],
        "types": [
            {
                "type": t,
                "visited": type_visited.get(t, 0),
                "total": type_total[t],
                "percentage": round(type_visited.get(t, 0) / type_total[t] * 100) if type_total[t] else 0,
            }
            for t in sorted(type_total.keys(), key=lambda x: -type_total[x])
        ],
        "must_see": {
            "visited": must_see_visited,
            "total": must_see_total,
            "percentage": round(must_see_visited / must_see_total * 100) if must_see_total else 0,
        },
        "state_breakdown": state_list,
    }
