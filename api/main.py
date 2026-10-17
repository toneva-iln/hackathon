"""Vitals streaming API.

Reads patients and vitals from the shared SQLite database (populated by
scripts/generate_vitals_stream.py), detects anomalies, and pushes
real-time updates to connected frontends via WebSocket.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import sqlite3
import os

DB_PATH = os.environ.get(
    "VITALS_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "vitals.db"),
)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# ---------------------------------------------------------------------------
# In-memory caches (populated from DB, kept current by the poll loop)
# ---------------------------------------------------------------------------

patients: dict[str, dict[str, Any]] = {}
vitals_history: dict[str, list[dict]] = defaultdict(list)
active_alerts: dict[str, list[dict]] = defaultdict(list)
alert_history: dict[str, list[dict]] = defaultdict(list)
last_seen_ts: dict[str, str] = {}

MAX_HISTORY = 300
POLL_INTERVAL = 1.0

# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "heart_rate": {"low": 50, "high": 110, "critical_low": 40, "critical_high": 150},
    "systolic_bp": {"low": 90, "high": 140, "critical_low": 80, "critical_high": 180},
    "diastolic_bp": {"low": 60, "high": 90, "critical_low": 50, "critical_high": 120},
    "spo2": {"low": 93, "high": 100, "critical_low": 88, "critical_high": 101},
    "temperature": {"low": 96.8, "high": 100.4, "critical_low": 95.0, "critical_high": 103.0},
    "respiratory_rate": {"low": 12, "high": 20, "critical_low": 8, "critical_high": 30},
}

ALERT_DESCRIPTIONS = {
    "heart_rate": {
        "high": "Tachycardia detected — elevated heart rate may indicate stress, fever, dehydration, or cardiac arrhythmia.",
        "low": "Bradycardia detected — abnormally low heart rate may indicate heart block, medication effects, or hypothyroidism.",
        "critical_high": "CRITICAL: Severe tachycardia — heart rate dangerously elevated. Immediate assessment required.",
        "critical_low": "CRITICAL: Severe bradycardia — heart rate dangerously low. Risk of syncope or cardiac arrest.",
    },
    "systolic_bp": {
        "high": "Hypertension detected — elevated systolic pressure increases stroke and cardiac event risk.",
        "low": "Hypotension detected — low systolic pressure may cause dizziness, fainting, or organ hypoperfusion.",
        "critical_high": "CRITICAL: Hypertensive crisis — systolic BP dangerously high. Risk of organ damage.",
        "critical_low": "CRITICAL: Severe hypotension — systolic BP dangerously low. Risk of shock.",
    },
    "diastolic_bp": {
        "high": "Elevated diastolic pressure — sustained elevation increases cardiovascular risk.",
        "low": "Low diastolic pressure — may indicate arterial stiffness or aortic regurgitation.",
        "critical_high": "CRITICAL: Diastolic crisis — dangerously elevated diastolic pressure.",
        "critical_low": "CRITICAL: Severe diastolic hypotension.",
    },
    "spo2": {
        "low": "Hypoxemia detected — oxygen saturation below normal. May indicate respiratory compromise.",
        "critical_low": "CRITICAL: Severe hypoxemia — SpO2 dangerously low. Supplemental oxygen and immediate intervention required.",
    },
    "temperature": {
        "high": "Fever detected — elevated temperature may indicate infection or inflammatory response.",
        "low": "Hypothermia detected — body temperature below normal range.",
        "critical_high": "CRITICAL: Hyperpyrexia — temperature dangerously elevated. Risk of organ damage.",
        "critical_low": "CRITICAL: Severe hypothermia — risk of cardiac arrhythmia and organ failure.",
    },
    "respiratory_rate": {
        "high": "Tachypnea detected — rapid breathing may indicate respiratory distress, pain, or metabolic acidosis.",
        "low": "Bradypnea detected — slow breathing may indicate CNS depression or medication effects.",
        "critical_high": "CRITICAL: Severe tachypnea — respiratory rate dangerously elevated. Assess for respiratory failure.",
        "critical_low": "CRITICAL: Severe bradypnea — respiratory rate dangerously low. Risk of respiratory arrest.",
    },
}

SEPSIS_SCREEN_CRITERIA = {
    "heart_rate": lambda v: v > 90,
    "temperature": lambda v: v > 100.4 or v < 96.8,
    "respiratory_rate": lambda v: v > 20,
    "systolic_bp": lambda v: v < 100,
}


def row_to_reading(row: sqlite3.Row) -> dict:
    """Convert a DB row into the reading dict used throughout the API."""
    return {
        "reading_id": row["id"],
        "patient_id": row["patient_id"],
        "device_id": row["device_id"],
        "device_type": row["device_type"],
        "timestamp": row["timestamp"],
        "vitals": {
            "heart_rate": {"value": row["heart_rate"], "unit": "bpm"},
            "systolic_bp": {"value": row["systolic_bp"], "unit": "mmHg"},
            "diastolic_bp": {"value": row["diastolic_bp"], "unit": "mmHg"},
            "spo2": {"value": row["spo2"], "unit": "%"},
            "temperature": {"value": row["temperature"], "unit": "°F"},
            "respiratory_rate": {"value": row["respiratory_rate"], "unit": "breaths/min"},
        },
        "anomaly": row["anomaly"],
    }


def detect_anomalies(reading: dict) -> list[dict]:
    alerts = []
    vitals = reading["vitals"]
    now = reading["timestamp"]

    for vital_name, thresholds in THRESHOLDS.items():
        value = vitals[vital_name]["value"]
        unit = vitals[vital_name]["unit"]

        severity = None
        direction = None

        if value <= thresholds.get("critical_low", -math.inf):
            severity = "critical"
            direction = "critical_low"
        elif value >= thresholds.get("critical_high", math.inf):
            severity = "critical"
            direction = "critical_high"
        elif value < thresholds["low"]:
            severity = "warning"
            direction = "low"
        elif value > thresholds["high"]:
            severity = "warning"
            direction = "high"

        if severity and direction:
            desc = ALERT_DESCRIPTIONS.get(vital_name, {}).get(direction, "Abnormal reading detected.")
            threshold_val = thresholds.get(direction) or thresholds.get(direction.replace("critical_", ""))
            alerts.append({
                "id": str(uuid.uuid4()),
                "vital": vital_name,
                "value": value,
                "unit": unit,
                "severity": severity,
                "direction": direction,
                "threshold": threshold_val,
                "description": desc,
                "timestamp": now,
                "reading_id": reading["reading_id"],
            })

    hits = sum(
        1 for vital_name, check in SEPSIS_SCREEN_CRITERIA.items()
        if vital_name in vitals and check(vitals[vital_name]["value"])
    )
    if hits >= 3:
        alerts.append({
            "id": str(uuid.uuid4()),
            "vital": "sepsis_screen",
            "value": hits,
            "unit": "criteria met",
            "severity": "critical",
            "direction": "high",
            "threshold": 3,
            "description": (
                f"SEPSIS SCREENING ALERT — {hits}/4 SIRS criteria met. "
                "Elevated HR, abnormal temperature, tachypnea, and/or hypotension detected simultaneously. "
                "Immediate clinical assessment, blood cultures, and lactate measurement recommended."
            ),
            "timestamp": now,
            "reading_id": reading["reading_id"],
        })

    return alerts


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.remove(ws)

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Load patients from DB and poll for new vitals readings
# ---------------------------------------------------------------------------

def load_patients() -> None:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, first_name, last_name, date_of_birth, sex, room, "
        "primary_diagnosis, admission_date, device_id, device_type "
        "FROM patients ORDER BY last_name, first_name"
    ).fetchall()
    conn.close()

    for row in rows:
        pid = row["id"]
        patients[pid] = {
            "patient_id": pid,
            "name": f"{row['first_name']} {row['last_name']}",
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "date_of_birth": row["date_of_birth"],
            "sex": row["sex"],
            "age": _calculate_age(row["date_of_birth"]),
            "room": row["room"],
            "primary_diagnosis": row["primary_diagnosis"],
            "admission_date": row["admission_date"],
            "device_id": row["device_id"],
            "device_type": row["device_type"],
            "status": "stable",
        }
        last_seen_ts[pid] = ""


def _calculate_age(dob_str: str) -> int:
    from datetime import date
    parts = dob_str.split("-")
    dob = date(int(parts[0]), int(parts[1]), int(parts[2]))
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


async def _poll_vitals_loop() -> None:
    """Poll the DB for new vitals readings written by the generator."""
    while True:
        conn = get_db()
        for pid in list(patients.keys()):
            ts = last_seen_ts.get(pid, "")
            rows = conn.execute(
                "SELECT * FROM vitals_readings "
                "WHERE patient_id = ? AND timestamp > ? "
                "ORDER BY timestamp ASC",
                (pid, ts),
            ).fetchall()

            for row in rows:
                reading = row_to_reading(row)
                last_seen_ts[pid] = row["timestamp"]

                vitals_history[pid].append(reading)
                if len(vitals_history[pid]) > MAX_HISTORY:
                    vitals_history[pid] = vitals_history[pid][-MAX_HISTORY:]

                alerts = detect_anomalies(reading)

                if alerts:
                    active_alerts[pid] = alerts
                    alert_history[pid].extend(alerts)
                    if len(alert_history[pid]) > 200:
                        alert_history[pid] = alert_history[pid][-200:]
                    worst = max(alerts, key=lambda a: 1 if a["severity"] == "critical" else 0)
                    patients[pid]["status"] = worst["severity"]
                else:
                    if active_alerts.get(pid):
                        active_alerts[pid] = []
                    patients[pid]["status"] = "stable"

                await manager.broadcast({
                    "type": "vitals_update",
                    "patient_id": pid,
                    "reading": reading,
                    "alerts": alerts,
                    "status": patients[pid]["status"],
                })

        conn.close()
        await asyncio.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_patients()
    task = asyncio.create_task(_poll_vitals_loop())
    yield
    task.cancel()


app = FastAPI(title="Vitals Streaming API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/api/patients")
async def list_patients() -> list[dict]:
    result = []
    for pid, p in patients.items():
        alert_count = len(active_alerts.get(pid, []))
        worst_severity = "stable"
        if active_alerts.get(pid):
            if any(a["severity"] == "critical" for a in active_alerts[pid]):
                worst_severity = "critical"
            else:
                worst_severity = "warning"
        result.append({**p, "alert_count": alert_count, "status": worst_severity})
    return result


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str) -> dict:
    p = patients.get(patient_id)
    if not p:
        return {"error": "not found"}
    latest = vitals_history[patient_id][-1] if vitals_history[patient_id] else None
    return {
        **p,
        "latest_vitals": latest,
        "active_alerts": active_alerts.get(patient_id, []),
        "alert_history": alert_history.get(patient_id, [])[-50:],
    }


@app.get("/api/patients/{patient_id}/vitals")
async def get_vitals_history(patient_id: str) -> list[dict]:
    return vitals_history.get(patient_id, [])


@app.get("/api/patients/{patient_id}/alerts")
async def get_alerts(patient_id: str) -> dict:
    return {
        "active": active_alerts.get(patient_id, []),
        "history": alert_history.get(patient_id, [])[-50:],
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
