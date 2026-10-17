"""Vitals streaming API.

Ingests synthetic vitals from the generator, detects anomalies, and pushes
real-time updates to connected frontends via WebSocket.
"""

from __future__ import annotations

import asyncio
import math
import random
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(application: FastAPI):
    names = random.sample(PATIENT_NAMES, NUM_PATIENTS)
    for name in names:
        pid = str(uuid.uuid4())
        sim = PatientSimulator(pid, name)
        simulators.append(sim)
        patients[pid] = {
            "patient_id": pid,
            "name": name,
            "age": sim.age,
            "room": sim.room,
            "device_id": sim.device_id,
            "device_type": sim.device_type,
            "status": "stable",
        }
    task = asyncio.create_task(_simulation_loop())
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
# In-memory stores
# ---------------------------------------------------------------------------

patients: dict[str, dict[str, Any]] = {}
vitals_history: dict[str, list[dict]] = defaultdict(list)
active_alerts: dict[str, list[dict]] = defaultdict(list)
alert_history: dict[str, list[dict]] = defaultdict(list)

MAX_HISTORY = 300

# ---------------------------------------------------------------------------
# Anomaly detection thresholds
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

    # Sepsis screening
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
# Built-in vitals simulator (runs in-process, no external script needed)
# ---------------------------------------------------------------------------

DEVICE_TYPES = [
    "bp_cuff_omron_x5",
    "pulse_ox_masimo_radical",
    "temp_braun_thermoscan",
    "multiparams_philips_mx800",
    "wearable_apple_watch_ultra",
    "wearable_fitbit_sense",
]

PATIENT_NAMES = [
    "Eleanor Vance", "Marcus Chen", "Sofia Rodriguez", "James Okafor",
    "Amara Patel", "Henrik Lindqvist", "Yuki Tanaka", "Olga Petrova",
    "David Mensah", "Claire Dubois", "Raj Krishnan", "Fatima Al-Rashid",
]

ANOMALY_PROFILES = {
    "hypertensive_crisis": {
        "systolic_bp": (180, 220), "diastolic_bp": (110, 140), "heart_rate": (90, 130),
    },
    "bradycardia": {"heart_rate": (30, 50)},
    "tachycardia": {"heart_rate": (120, 180)},
    "hypoxemia": {"spo2": (82, 90), "respiratory_rate": (22, 35)},
    "fever": {"temperature": (101.0, 104.5), "heart_rate": (90, 120)},
    "sepsis_early": {
        "heart_rate": (95, 130), "temperature": (100.5, 103.5),
        "respiratory_rate": (22, 30), "systolic_bp": (85, 100), "spo2": (90, 95),
    },
}


class PatientSimulator:
    def __init__(self, patient_id: str, name: str) -> None:
        self.patient_id = patient_id
        self.name = name
        self.device_id = f"DEV-{uuid.uuid4().hex[:8].upper()}"
        self.device_type = random.choice(DEVICE_TYPES)
        self.age = random.randint(28, 85)
        self.room = f"{random.choice(['A', 'B', 'C', 'D'])}-{random.randint(100, 450)}"
        self.baseline = {
            "heart_rate": random.gauss(75, 8),
            "systolic_bp": random.gauss(120, 12),
            "diastolic_bp": random.gauss(80, 8),
            "spo2": min(100.0, random.gauss(97.5, 1.0)),
            "temperature": random.gauss(98.6, 0.4),
            "respiratory_rate": random.gauss(16, 2),
        }
        self._tick = 0
        self._active_anomaly: str | None = None
        self._anomaly_ticks_left = 0

    def generate_reading(self, anomaly_rate: float) -> dict:
        self._tick += 1

        if self._anomaly_ticks_left > 0:
            self._anomaly_ticks_left -= 1
            if self._anomaly_ticks_left == 0:
                self._active_anomaly = None
        elif random.random() < anomaly_rate:
            self._active_anomaly = random.choice(list(ANOMALY_PROFILES.keys()))
            self._anomaly_ticks_left = random.randint(3, 12)

        def drift(base: float, amp: float, period: float) -> float:
            return base + amp * math.sin(2 * math.pi * self._tick / period)

        hr = drift(self.baseline["heart_rate"], 3.0, 60)
        sys_bp = drift(self.baseline["systolic_bp"], 5.0, 90)
        dia_bp = drift(self.baseline["diastolic_bp"], 3.0, 90)
        spo2 = drift(self.baseline["spo2"], 0.5, 120)
        temp = drift(self.baseline["temperature"], 0.2, 200)
        rr = drift(self.baseline["respiratory_rate"], 1.0, 45)

        vals = {"heart_rate": hr, "systolic_bp": sys_bp, "diastolic_bp": dia_bp,
                "spo2": spo2, "temperature": temp, "respiratory_rate": rr}

        if self._active_anomaly:
            profile = ANOMALY_PROFILES[self._active_anomaly]
            progress = 1 - (self._anomaly_ticks_left / 12)
            blend = min(1.0, progress * 1.5)
            for key, (lo, hi) in profile.items():
                vals[key] = vals[key] * (1 - blend) + random.uniform(lo, hi) * blend

        for key in vals:
            vals[key] += random.gauss(0, 1.0)

        vals["spo2"] = max(70, min(100, vals["spo2"]))
        vals["heart_rate"] = max(20, min(250, vals["heart_rate"]))
        vals["systolic_bp"] = max(60, min(260, vals["systolic_bp"]))
        vals["diastolic_bp"] = max(30, min(180, vals["diastolic_bp"]))
        vals["temperature"] = max(90, min(110, vals["temperature"]))
        vals["respiratory_rate"] = max(4, min(60, vals["respiratory_rate"]))

        units = {
            "heart_rate": "bpm", "systolic_bp": "mmHg", "diastolic_bp": "mmHg",
            "spo2": "%", "temperature": "°F", "respiratory_rate": "breaths/min",
        }

        return {
            "reading_id": str(uuid.uuid4()),
            "patient_id": self.patient_id,
            "device_id": self.device_id,
            "device_type": self.device_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vitals": {k: {"value": round(v, 1), "unit": units[k]} for k, v in vals.items()},
            "anomaly": self._active_anomaly,
        }


NUM_PATIENTS = 8
ANOMALY_RATE = 0.15
TICK_INTERVAL = 2.0

simulators: list[PatientSimulator] = []


async def _simulation_loop() -> None:
    while True:
        for sim in simulators:
            reading = sim.generate_reading(ANOMALY_RATE)
            pid = sim.patient_id

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

        await asyncio.sleep(TICK_INTERVAL)


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
