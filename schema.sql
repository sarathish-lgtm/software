CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('patient', 'doctor', 'admin')),
    phone         TEXT,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS departments (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS doctors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL UNIQUE REFERENCES users(id),
    department_id INTEGER NOT NULL REFERENCES departments(id),
    qualification TEXT,
    fee           INTEGER NOT NULL DEFAULT 300,
    start_hour    INTEGER NOT NULL DEFAULT 9,      -- clinic opens (24h)
    end_hour      INTEGER NOT NULL DEFAULT 17,     -- clinic closes (24h)
    days          TEXT NOT NULL DEFAULT '0,1,2,3,4', -- 0=Mon ... 6=Sun
    active        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS appointments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id   INTEGER NOT NULL REFERENCES users(id),
    doctor_id    INTEGER NOT NULL REFERENCES doctors(id),
    appt_date    TEXT NOT NULL,                    -- YYYY-MM-DD
    appt_time    TEXT NOT NULL,                    -- HH:MM
    reason       TEXT,
    status       TEXT NOT NULL DEFAULT 'Booked'
                 CHECK (status IN ('Booked', 'Completed', 'Cancelled')),
    prescription TEXT,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A doctor cannot have two live appointments at the same date and time.
-- Cancelled appointments free the slot again.
CREATE UNIQUE INDEX IF NOT EXISTS ux_live_slot
    ON appointments (doctor_id, appt_date, appt_time)
    WHERE status <> 'Cancelled';
