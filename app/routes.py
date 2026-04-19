from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db import get_db
from app.models import Trip
from app.itinerary import (
    generate_itinerary,
    load_pois,
    choose_replacement,
    rebuild_day_respecting_locks,
)

router = APIRouter()


# ---------- Request Models ----------

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


# ---------- Endpoints ----------

@router.post("/trips", status_code=201)
def create_trip(request: TripRequest, db: Session = Depends(get_db)):
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

    trip = Trip(
        city="Wellington",
        days=request.days,
        pace=request.pace,
        budget_nzd=request.budget_nzd,
        result=result,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    return {"trip_id": trip.id, "city": "Wellington", "days": request.days, **result}


@router.get("/trips/{trip_id}")
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return {
        "trip_id": trip.id,
        "city": trip.city,
        "days": trip.days,
        "pace": trip.pace,
        "budget_nzd": trip.budget_nzd,
        **trip.result,
        "created_at": trip.created_at,
    }


@router.put("/trips/{trip_id}/replace")
def replace_activity(trip_id: int, request: ReplaceRequest, db: Session = Depends(get_db)):
    if request.slot not in ("morning", "afternoon", "evening"):
        raise HTTPException(status_code=400, detail="slot must be morning/afternoon/evening")

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    result = trip.result
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
            budget_nzd=trip.budget_nzd,
            days=trip.days,
            constraints=result.get("constraints_applied", {}),
            preferences=request.preferences,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    itinerary[day_key][request.slot] = new_item
    trip.result = result
    flag_modified(trip, "result")
    db.commit()
    db.refresh(trip)

    return {"trip_id": trip.id, "updated": True, **trip.result}


@router.post("/trips/{trip_id}/rebuild-day")
def rebuild_day(trip_id: int, request: RebuildDayRequest, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    result = trip.result
    result.setdefault("locked_slots", [])
    all_pois = load_pois()

    try:
        updated = rebuild_day_respecting_locks(
            day_number=request.day,
            original_result=result,
            all_pois=all_pois,
            days=trip.days,
            budget_nzd=trip.budget_nzd,
            pace=result.get("pace", "balanced"),
            interests=result.get("interests", {}),
            constraints=result.get("constraints_applied", {}),
            locked_slots=result.get("locked_slots", []),
            keep_used=True,
            force_change=request.force_change,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    trip.result = updated
    flag_modified(trip, "result")
    db.commit()
    db.refresh(trip)

    return {"trip_id": trip.id, "updated": True, **trip.result}


@router.post("/trips/{trip_id}/lock-slot")
def lock_slot(trip_id: int, request: LockSlotRequest, db: Session = Depends(get_db)):
    if request.slot not in ("morning", "afternoon", "evening"):
        raise HTTPException(status_code=400, detail="slot must be morning/afternoon/evening")

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    result = trip.result
    result.setdefault("locked_slots", [])

    key = f"day_{request.day}:{request.slot}"
    if key not in result["locked_slots"]:
        result["locked_slots"].append(key)

    trip.result = result
    flag_modified(trip, "result")
    db.commit()
    db.refresh(trip)

    return {"trip_id": trip.id, "locked_slots": result["locked_slots"]}


@router.post("/trips/{trip_id}/unlock-slot")
def unlock_slot(trip_id: int, request: LockSlotRequest, db: Session = Depends(get_db)):
    if request.slot not in ("morning", "afternoon", "evening"):
        raise HTTPException(status_code=400, detail="slot must be morning/afternoon/evening")

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    result = trip.result
    key = f"day_{request.day}:{request.slot}"
    result["locked_slots"] = [x for x in result.get("locked_slots", []) if x != key]

    trip.result = result
    flag_modified(trip, "result")
    db.commit()
    db.refresh(trip)

    return {"trip_id": trip.id, "locked_slots": result["locked_slots"]}