![CI](https://github.com/ChSuhasini/travel-planner/actions/workflows/ci.yml/badge.svg)

# Travel Planner API

A REST API that generates personalised day-by-day travel itineraries for Wellington, New Zealand.

## What it does

Users provide their trip preferences and the API returns a complete itinerary:
- Number of days (1-5)
- Budget in NZD
- Travel pace (relaxed, balanced, packed)
- Interests (food, nature, culture, views, adventure, shopping)
- Constraints (kid friendly, indoor only, avoid high walking)

## Tech Stack

- **Python** → primary language
- **FastAPI** → REST API framework
- **PostgreSQL** → database
- **psycopg2** → connects Python to PostgreSQL with raw SQL
- **Pydantic** → request validation
- **pytest** → automated testing
- **GitHub Actions** → CI/CD pipeline
- **Docker** → database containerisation

## Project Structure

travel-planner/
├── app/
│   ├── main.py        → API entry point
│   ├── db.py          → database connection
│   ├── routes.py      → API endpoints
│   ├── itinerary.py   → trip generation logic
│   └── data/
│       └── wellington_pois_v1.json → Wellington attractions
├── tests/
│   ├── conftest.py    → pytest fixtures and setup
│   └── test_trips.py  → API tests
├── .github/
│   └── workflows/
│       └── ci.yml     → GitHub Actions CI pipeline
├── schema.sql         → database table definitions
├── docker-compose.yml → database container setup
├── requirements.txt   → Python dependencies
└── .env               → environment variables (not in git)

## How to Run

### 1. Clone the repository
```bash
git clone https://github.com/ChSuhasini/travel-planner.git
cd travel-planner
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up environment variables
Create a `.env` file in the root folder:
DB_HOST=localhost
DB_NAME=travelplanner
DB_USER=traveller
DB_PASSWORD=travelpass
DB_PORT=5432

### 5. Set up the database
```bash
psql -U traveller -d travelplanner -f schema.sql
```

### 6. Run the API
```bash
uvicorn app.main:app --reload
```

### 7. Open API docs
http://localhost:8000/docs

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /trips | Generate and save a trip |
| GET | /trips/{id} | Get a saved trip |
| PUT | /trips/{id}/replace | Replace one activity |
| POST | /trips/{id}/rebuild-day | Rebuild an entire day |
| POST | /trips/{id}/lock-slot | Lock an activity |
| POST | /trips/{id}/unlock-slot | Unlock an activity |

## Example Request

POST /trips
```json
{
    "days": 2,
    "budget_nzd": 500,
    "pace": "balanced",
    "interests": {
        "food": 5,
        "nature": 3,
        "culture": 4
    },
    "constraints": {
        "kid_friendly": false
    }
}
```

## Example Response

```json
{
    "trip_id": 1,
    "city": "Wellington",
    "estimated_total_cost_nzd": 150,
    "itinerary": {
        "day_1": {
            "morning": {"name": "Te Papa Tongarewa Museum"},
            "afternoon": {"name": "Cuba Street Food & Coffee"},
            "evening": {"name": "Wellington Night Markets"}
        }
    }
}
```

## Algorithm

The itinerary engine scores each Wellington attraction based on:
1. **Preference match** → higher score if place tags match user interests
2. **Cost penalty** → expensive places penalised for tight budgets
3. **Indoor bonus** → small bonus for indoor places (Wellington is rainy!)

Places are ranked by score and filled into days respecting the pace time limit. Same place never appears twice across the whole trip.

## Running Tests

```bash
pytest tests/ -v
```

Tests cover:
- Creating a trip
- Retrieving a saved trip
- 404 handling for missing trips
- Input validation
- Replacing an activity
- Locking a slot and preventing replacement

## CI/CD

This project uses GitHub Actions for continuous integration. Every push to `main` automatically:
1. Sets up Python 3.12
2. Starts a PostgreSQL database
3. Creates database tables
4. Runs all tests

See the Actions tab for test results.

