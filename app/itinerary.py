import json
from pathlib import Path
from typing import Dict, List, Any

DATA_PATH = Path(__file__).parent / "data" / "wellington_pois_v1.json"

COST_SCORE = {
    "free": 0,
    "cheap": 1,
    "medium": 2,
    "expensive": 3,
}

PACE_MINUTES = {
    "relaxed": 7 * 60,
    "balanced": 10 * 60,
    "packed": 13 * 60,
}

BUFFER_PER_ACTIVITY_MIN = 15

def load_pois() -> List[Dict[str, Any]]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        pois = json.load(f)
    if not isinstance(pois, list):
        raise ValueError("POI dataset must be a JSON list.")
    return pois


def est_cost_nzd(cost_level: str) -> int:
    if cost_level == "free":
        return 0
    elif cost_level == "cheap":
        return 50
    elif cost_level == "medium":
        return 120
    else:
        return 220


def activity_minutes(poi: Dict[str, Any]) -> int:
    return int(poi.get("avgDurationMin", 60))


def fits_day(day_items: List[Dict[str, Any]], pace: str) -> bool:
    cap = PACE_MINUTES.get(pace, PACE_MINUTES["balanced"])
    total = sum(activity_minutes(p) + BUFFER_PER_ACTIVITY_MIN for p in day_items)
    return total <= cap


def day_minutes(day_items: List[Dict[str, Any]]) -> int:
    return sum(activity_minutes(p) + BUFFER_PER_ACTIVITY_MIN for p in day_items)

def passes_constraints(poi: Dict[str, Any], constraints: Dict[str, bool]) -> bool:
    if constraints.get("kid_friendly") and not poi.get("kidFriendly", False):
        return False
    if constraints.get("accessibility_friendly") and poi.get("accessibilityFriendly") is not True:
        return False
    if constraints.get("indoor_only") and not poi.get("indoor", False):
        return False
    if constraints.get("avoid_high_walking") and poi.get("walkingLevel") == "high":
        return False
    return True

def generate_itinerary(
    days: int,
    budget_nzd: int,
    pace: str,
    interests: Dict[str, int],
    constraints: Dict[str, bool]
) -> Dict[str, Any]:

    pois = load_pois()

    # Step 1: Filter by constraints
    filtered = [p for p in pois if passes_constraints(p, constraints)]
    if len(filtered) < days * 3:
        raise ValueError(f"Not enough POIs after filtering. Need {days*3}, have {len(filtered)}")

    # Step 2: Score and sort
    scored = sorted(
        filtered,
        key=lambda p: score_poi(p, interests, budget_nzd, days),
        reverse=True
    )

    itinerary: Dict[str, Any] = {}
    used_ids = set()

    # Step 3: Build each day
    for d in range(1, days + 1):
        day_items: List[Dict[str, Any]] = []

        for p in scored:
            if p["id"] in used_ids:
                continue
            tentative = day_items + [p]
            if fits_day(tentative, pace):
                day_items.append(p)
                used_ids.add(p["id"])
            if len(day_items) == 3:
                break

        # Step 4: Fill if less than 3 activities
        if len(day_items) < 3:
            fillers = sorted(
                [p for p in scored if p["id"] not in used_ids],
                key=lambda p: (est_cost_nzd(p.get("costLevel", "medium")), activity_minutes(p)),
            )
            for p in fillers:
                if len(day_items) == 3:
                    break
                tentative = day_items + [p]
                if fits_day(tentative, pace):
                    day_items.append(p)
                    used_ids.add(p["id"])

        itinerary[f"day_{d}"] = {
            "morning": day_items[0] if len(day_items) > 0 else None,
            "afternoon": day_items[1] if len(day_items) > 1 else None,
            "evening": day_items[2] if len(day_items) > 2 else None,
            "day_minutes": day_minutes(day_items),
            "pace_cap_minutes": PACE_MINUTES.get(pace, PACE_MINUTES["balanced"]),
        }

    # Step 5: Calculate total cost
    all_items = []
    for day in itinerary.values():
        for slot in ("morning", "afternoon", "evening"):
            if day.get(slot):
                all_items.append(day[slot])

    total_est = sum(est_cost_nzd(p.get("costLevel", "medium")) for p in all_items)

    warnings = []
    if budget_nzd > 0 and total_est > budget_nzd:
        warnings.append(f"Estimated cost ${total_est} NZD exceeds your budget of ${budget_nzd} NZD.")

    return {
        "pace": pace,
        "budget_nzd": budget_nzd,
        "estimated_total_cost_nzd": total_est,
        "warnings": warnings,
        "interests": interests,
        "constraints_applied": constraints,
        "itinerary": itinerary,
        "locked_slots": [],
    }

def choose_replacement(
    all_pois: List[Dict[str, Any]],
    used_ids: set,
    interests: Dict[str, int],
    budget_nzd: int,
    days: int,
    constraints: Dict[str, bool],
    preferences: Dict[str, bool],
) -> Dict[str, Any]:

    candidates = []
    for p in all_pois:
        if p["id"] in used_ids:
            continue
        if not passes_constraints(p, constraints):
            continue
        if preferences.get("indoor") and not p.get("indoor", False):
            continue
        if preferences.get("cheaper") and p.get("costLevel") not in ("free", "cheap"):
            continue
        if preferences.get("shorter") and int(p.get("avgDurationMin", 60)) > 90:
            continue
        candidates.append(p)

    if not candidates:
        raise ValueError("No replacement candidates found for given preferences and constraints.")

    candidates.sort(
        key=lambda p: score_poi(p, interests, budget_nzd, days),
        reverse=True
    )
    return candidates[0]


def rebuild_day_respecting_locks(
    day_number: int,
    original_result: Dict[str, Any],
    all_pois: List[Dict[str, Any]],
    days: int,
    budget_nzd: int,
    pace: str,
    interests: Dict[str, int],
    constraints: Dict[str, bool],
    locked_slots: List[str],
    keep_used: bool = True,
    force_change: bool = True,
) -> Dict[str, Any]:

    itinerary = original_result["itinerary"]
    day_key = f"day_{day_number}"

    if day_key not in itinerary:
        raise ValueError("Invalid day number.")

    locked_set = set(locked_slots or [])
    day_locked = {
        slot for slot in ("morning", "afternoon", "evening")
        if f"{day_key}:{slot}" in locked_set
    }

    used_ids = set()
    if keep_used:
        for k, day in itinerary.items():
            for slot in ("morning", "afternoon", "evening"):
                item = day.get(slot)
                if not item:
                    continue
                if k != day_key or slot in day_locked:
                    used_ids.add(item["id"])

    for slot in ("morning", "afternoon", "evening"):
        current = itinerary[day_key].get(slot)

        if slot in day_locked:
            if current:
                used_ids.add(current["id"])
            continue

        banned_id = current.get("id") if force_change and current else None

        used_for_this = set(used_ids)
        if current:
            used_for_this.discard(current["id"])

        pool = [
            p for p in all_pois
            if passes_constraints(p, constraints)
            and p["id"] != banned_id
            and p["id"] not in used_for_this
        ]

        if not pool:
            pool = [
                p for p in all_pois
                if passes_constraints(p, constraints)
                and p["id"] != banned_id
            ]

        if not pool:
            continue

        pool.sort(
            key=lambda p: score_poi(p, interests, budget_nzd, days),
            reverse=True
        )

        tmp_items = [
            itinerary[day_key].get(s)
            for s in ("morning", "afternoon", "evening")
            if s != slot and itinerary[day_key].get(s)
        ]

        chosen = next(
            (p for p in pool if fits_day(tmp_items + [p], pace)),
            pool[0]
        )

        itinerary[day_key][slot] = chosen
        used_ids.add(chosen["id"])

    day_items = [
        itinerary[day_key][s]
        for s in ("morning", "afternoon", "evening")
        if itinerary[day_key].get(s)
    ]

    itinerary[day_key]["day_minutes"] = day_minutes(day_items)
    itinerary[day_key]["pace_cap_minutes"] = PACE_MINUTES.get(pace, PACE_MINUTES["balanced"])

    all_items = [
        day[s]
        for day in itinerary.values()
        for s in ("morning", "afternoon", "evening")
        if day.get(s)
    ]

    total_est = sum(est_cost_nzd(p.get("costLevel", "medium")) for p in all_items)
    warnings = []
    if budget_nzd > 0 and total_est > budget_nzd:
        warnings.append(f"Estimated cost ${total_est} NZD exceeds your budget of ${budget_nzd} NZD.")

    original_result["estimated_total_cost_nzd"] = total_est
    original_result["warnings"] = warnings
    original_result["itinerary"] = itinerary

    return original_result