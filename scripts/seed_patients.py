#!/usr/bin/env python3
"""Seed the patients table with synthetic patient records."""

from __future__ import annotations

import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import get_connection, init_db

DEVICE_TYPES = [
    "bp_cuff_omron_x5",
    "pulse_ox_masimo_radical",
    "temp_braun_thermoscan",
    "multiparams_philips_mx800",
    "wearable_apple_watch_ultra",
    "wearable_fitbit_sense",
]

PATIENTS = [
    {"first_name": "Eleanor", "last_name": "Vance", "dob": "1948-03-12", "sex": "F", "diagnosis": "Heart failure (post-discharge)"},
    {"first_name": "Marcus", "last_name": "Chen", "dob": "1961-07-24", "sex": "M", "diagnosis": "Post-CABG monitoring"},
    {"first_name": "Sofia", "last_name": "Rodriguez", "dob": "1975-11-08", "sex": "F", "diagnosis": "COPD exacerbation recovery"},
    {"first_name": "James", "last_name": "Okafor", "dob": "1958-01-30", "sex": "M", "diagnosis": "Hypertension management"},
    {"first_name": "Amara", "last_name": "Patel", "dob": "1942-09-15", "sex": "F", "diagnosis": "Post-sepsis discharge"},
    {"first_name": "Henrik", "last_name": "Lindqvist", "dob": "1970-05-03", "sex": "M", "diagnosis": "Atrial fibrillation monitoring"},
    {"first_name": "Yuki", "last_name": "Tanaka", "dob": "1983-12-20", "sex": "F", "diagnosis": "Post-cardiac surgery"},
    {"first_name": "Olga", "last_name": "Petrova", "dob": "1955-06-17", "sex": "F", "diagnosis": "Heart failure (stage C)"},
    {"first_name": "David", "last_name": "Mensah", "dob": "1966-02-28", "sex": "M", "diagnosis": "COPD with home O2"},
    {"first_name": "Claire", "last_name": "Dubois", "dob": "1950-08-04", "sex": "F", "diagnosis": "Post-hip replacement (DVT risk)"},
    {"first_name": "Raj", "last_name": "Krishnan", "dob": "1972-10-11", "sex": "M", "diagnosis": "Beta-blocker titration"},
    {"first_name": "Fatima", "last_name": "Al-Rashid", "dob": "1940-04-22", "sex": "F", "diagnosis": "Chronic kidney disease stage 3"},
]

ROOMS = [f"{wing}-{num}" for wing in ["A", "B", "C", "D"] for num in range(100, 450, 25)]


def seed() -> None:
    init_db()
    conn = get_connection()

    existing = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    if existing > 0:
        print(f"Patients table already has {existing} records. Skipping seed.")
        print("To re-seed, delete data/vitals.db and run again.")
        conn.close()
        return

    rooms = random.sample(ROOMS, len(PATIENTS))

    for i, p in enumerate(PATIENTS):
        conn.execute(
            """
            INSERT INTO patients (id, first_name, last_name, date_of_birth, sex, room, primary_diagnosis, admission_date, device_id, device_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                p["first_name"],
                p["last_name"],
                p["dob"],
                p["sex"],
                rooms[i],
                p["diagnosis"],
                "2026-10-14",
                f"DEV-{uuid.uuid4().hex[:8].upper()}",
                random.choice(DEVICE_TYPES),
            ),
        )

    conn.commit()
    conn.close()

    print(f"Seeded {len(PATIENTS)} patients into the database.")


if __name__ == "__main__":
    seed()
