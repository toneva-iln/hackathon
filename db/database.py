"""Shared SQLite database schema and connection helpers."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("VITALS_DB_PATH", str(Path(__file__).resolve().parent.parent / "data" / "vitals.db"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id              TEXT PRIMARY KEY,
            first_name      TEXT NOT NULL,
            last_name       TEXT NOT NULL,
            date_of_birth   TEXT NOT NULL,
            sex             TEXT NOT NULL CHECK (sex IN ('M', 'F')),
            room            TEXT NOT NULL,
            primary_diagnosis TEXT NOT NULL,
            admission_date  TEXT NOT NULL,
            device_id       TEXT NOT NULL,
            device_type     TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS vitals_readings (
            id              TEXT PRIMARY KEY,
            patient_id      TEXT NOT NULL REFERENCES patients(id),
            timestamp       TEXT NOT NULL,
            heart_rate      REAL NOT NULL,
            systolic_bp     REAL NOT NULL,
            diastolic_bp    REAL NOT NULL,
            spo2            REAL NOT NULL,
            temperature     REAL NOT NULL,
            respiratory_rate REAL NOT NULL,
            anomaly         TEXT,
            device_id       TEXT NOT NULL,
            device_type     TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_vitals_patient_ts
            ON vitals_readings(patient_id, timestamp DESC);
    """)
    conn.commit()
    conn.close()
