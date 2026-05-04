import json
import psycopg2
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict

from app.db import get_connection
from app.itinerary import generate_itinerary, load_pois, choose_replacement, rebuild_day_respecting_locks

router = APIRouter()

class TripRequest(BaseModel):
    days: int = Field(ge=1, le=5)
    budget_nzd: int = Field(ge=0, le=10000)
    pace: str = Field(default="balanced")
    interests: Dict[str, int] = Field(default_factory=lambda: {
        "food": 3,
        "nature": 3,
        "culture": 3,
        "views": 3,
        "adventure": 3,
        "shopping": 1,
    })
    constraints: Dict[str, bool] = Field(default_factory=dict)


class ReplaceRequest(BaseModel):
    day: int = Field(ge=1, le=5)
    slot: str
    preferences: Dict[str, bool] = Field(default_factory=dict)


class RebuildDayRequest(BaseModel):
    day: int = Field(ge=1, le=5)
    force_change: bool = True


class LockSlotRequest(BaseModel):
    day: int = Field(ge=1, le=5)
    slot: str

@router.post("/trips", status_code=201)
def create_trip(request: TripRequest):
    try:
        result = generate_itinerary(
            days=request.days,
            budget_nzd=request.budget_nzd,
            pace=request.pace,
            interests=request.interests,
            constraints=request.constraints,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO trips (city, days, pace, budget_nzd, result)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            ("Wellington", request.days, request.pace, request.budget_nzd, json.dumps(result))
        )
        row = cur.fetchone()
        trip_id = row[0]
        created_at = row[1]
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        cur.close()
        conn.close()

    return {"trip_id": trip_id, "city": "Wellington", "days": request.days, "created_at": str(created_at), **result}

@router.get("/trips/{trip_id}")
def get_trip(trip_id: int):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT id, city, days, pace, budget_nzd, result, created_at FROM trips WHERE id = %s",
            (trip_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trip not found")

        return {
            "trip_id": row[0],
            "city": row[1],
            "days": row[2],
            "pace": row[3],
            "budget_nzd": row[4],
            **row[5],
            "created_at": str(row[6]),
        }
    finally:
        cur.close()
        conn.close()


@router.put("/trips/{trip_id}/replace")
def replace_activity(trip_id: int, request: ReplaceRequest):
    if request.slot not in ("morning", "afternoon", "evening"):
        raise HTTPException(status_code=400, detail="slot must be morning/afternoon/evening")

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT result, days, budget_nzd FROM trips WHERE id = %s", (trip_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trip not found")

        result = row[0]
        days = row[1]
        budget_nzd = row[2]
        itinerary = result["itinerary"]
        day_key = f"day_{request.day}"

        if day_key not in itinerary:
            raise HTTPException(status_code=400, detail="Invalid day")

        locked_slots = set(result.get("locked_slots", []))
        slot_key = f"{day_key}:{request.slot}"
        if slot_key in locked_slots:
            raise HTTPException(status_code=400, detail="This slot is locked and cannot be replaced.")

        used_ids = set()
        for day in itinerary.values():
            for k in ("morning", "afternoon", "evening"):
                if day.get(k):
                    used_ids.add(day[k]["id"])

        current = itinerary[day_key].get(request.slot)
        if current:
            used_ids.discard(current["id"])

        all_pois = load_pois()

        try:
            new_item = choose_replacement(
                all_pois=all_pois,
                used_ids=used_ids,
                interests=result.get("interests", {}),
                budget_nzd=budget_nzd,
                days=days,
                constraints=result.get("constraints_applied", {}),
                preferences=request.preferences,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        itinerary[day_key][request.slot] = new_item
        result["itinerary"] = itinerary

        cur.execute(
            "UPDATE trips SET result = %s WHERE id = %s",
            (json.dumps(result), trip_id)
        )
        conn.commit()

        return {"trip_id": trip_id, "updated": True, **result}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        cur.close()
        conn.close()

@router.post("/trips/{trip_id}/rebuild-day")
def rebuild_day(trip_id: int, request: RebuildDayRequest):
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT result, days, budget_nzd FROM trips WHERE id = %s", (trip_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trip not found")

        result = row[0]
        days = row[1]
        budget_nzd = row[2]
        result.setdefault("locked_slots", [])

        all_pois = load_pois()

        try:
            updated = rebuild_day_respecting_locks(
                day_number=request.day,
                original_result=result,
                all_pois=all_pois,
                days=days,
                budget_nzd=budget_nzd,
                pace=result.get("pace", "balanced"),
                interests=result.get("interests", {}),
                constraints=result.get("constraints_applied", {}),
                locked_slots=result.get("locked_slots", []),
                keep_used=True,
                force_change=request.force_change,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        cur.execute(
            "UPDATE trips SET result = %s WHERE id = %s",
            (json.dumps(updated), trip_id)
        )
        conn.commit()

        return {"trip_id": trip_id, "updated": True, **updated}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        cur.close()
        conn.close()
@router.post("/trips/{trip_id}/lock-slot")
def lock_slot(trip_id: int, request: LockSlotRequest):
    if request.slot not in ("morning", "afternoon", "evening"):
        raise HTTPException(status_code=400, detail="slot must be morning/afternoon/evening")

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT result FROM trips WHERE id = %s", (trip_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trip not found")

        result = row[0]
        result.setdefault("locked_slots", [])

        key = f"day_{request.day}:{request.slot}"
        if key not in result["locked_slots"]:
            result["locked_slots"].append(key)

        cur.execute(
            "UPDATE trips SET result = %s WHERE id = %s",
            (json.dumps(result), trip_id)
        )
        conn.commit()

        return {"trip_id": trip_id, "locked_slots": result["locked_slots"]}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        cur.close()
        conn.close()


@router.post("/trips/{trip_id}/unlock-slot")
def unlock_slot(trip_id: int, request: LockSlotRequest):
    if request.slot not in ("morning", "afternoon", "evening"):
        raise HTTPException(status_code=400, detail="slot must be morning/afternoon/evening")

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("SELECT result FROM trips WHERE id = %s", (trip_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trip not found")

        result = row[0]
        key = f"day_{request.day}:{request.slot}"
        result["locked_slots"] = [x for x in result.get("locked_slots", []) if x != key]

        cur.execute(
            "UPDATE trips SET result = %s WHERE id = %s",
            (json.dumps(result), trip_id)
        )
        conn.commit()

        return {"trip_id": trip_id, "locked_slots": result["locked_slots"]}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    finally:
        cur.close()
        conn.close()