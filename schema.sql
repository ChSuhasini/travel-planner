CREATE TABLE IF NOT EXISTS trips (
    id         SERIAL PRIMARY KEY,
    city       VARCHAR(100) NOT NULL,
    days       INTEGER NOT NULL,
    pace       VARCHAR(20) NOT NULL,
    budget_nzd INTEGER NOT NULL,
    result     JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);