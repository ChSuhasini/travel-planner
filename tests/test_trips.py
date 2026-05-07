import pytest


def test_create_trip(client):
    response = client.post("/trips", json={
        "days": 2,
        "budget_nzd": 500,
        "pace": "balanced",
        "interests": {
            "food": 3,
            "nature": 3,
            "culture": 3,
            "views": 3,
            "adventure": 3,
            "shopping": 1
        },
        "constraints": {}
    })

    assert response.status_code == 201
    data = response.json()
    assert "trip_id" in data
    assert data["city"] == "Wellington"
    assert data["days"] == 2
    assert "itinerary" in data


def test_get_trip(client):
    # First create a trip
    create = client.post("/trips", json={
        "days": 1,
        "budget_nzd": 300,
        "pace": "relaxed",
        "interests": {"food": 3, "nature": 3, "culture": 3, "views": 3, "adventure": 3, "shopping": 1},
        "constraints": {}
    })
    trip_id = create.json()["trip_id"]

    # Then get it
    response = client.get(f"/trips/{trip_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["trip_id"] == trip_id
    assert data["city"] == "Wellington"

def test_get_trip_not_found(client):
    response = client.get("/trips/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Trip not found"

def test_create_trip_invalid_days(client):
    response = client.post("/trips", json={
        "days": 10,
        "budget_nzd": 500,
        "pace": "balanced",
        "interests": {"food": 3, "nature": 3, "culture": 3, "views": 3, "adventure": 3, "shopping": 1},
        "constraints": {}
    })

    assert response.status_code == 422

def test_replace_activity(client):
    # First create a trip
    create = client.post("/trips", json={
        "days": 1,
        "budget_nzd": 500,
        "pace": "balanced",
        "interests": {"food": 3, "nature": 3, "culture": 3, "views": 3, "adventure": 3, "shopping": 1},
        "constraints": {}
    })
    trip_id = create.json()["trip_id"]
    original_morning = create.json()["itinerary"]["day_1"]["morning"]["id"]

    # Replace morning activity
    response = client.put(f"/trips/{trip_id}/replace", json={
        "day": 1,
        "slot": "morning",
        "preferences": {}
    })

    assert response.status_code == 200
    data = response.json()
    assert "itinerary" in data
    assert data["updated"] == True

def test_replace_locked_slot(client):
    # First create a trip
    create = client.post("/trips", json={
        "days": 1,
        "budget_nzd": 500,
        "pace": "balanced",
        "interests": {"food": 3, "nature": 3, "culture": 3, "views": 3, "adventure": 3, "shopping": 1},
        "constraints": {}
    })
    trip_id = create.json()["trip_id"]

    # Lock morning slot
    client.post(f"/trips/{trip_id}/lock-slot", json={
        "day": 1,
        "slot": "morning"
    })

    # Try to replace locked slot
    response = client.put(f"/trips/{trip_id}/replace", json={
        "day": 1,
        "slot": "morning",
        "preferences": {}
    })

    assert response.status_code == 400
    assert "locked" in response.json()["detail"].lower()