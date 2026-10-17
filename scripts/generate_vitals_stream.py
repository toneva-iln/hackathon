#!/usr/bin/env python3
"""Synthetic vitals streaming data generator.

Reads patients from the shared SQLite database and continuously writes
vitals readings into the vitals_readings table. Also emits JSON-lines
to stdout (or a file) for debugging.

Usage:
  # Seed patients first
  python scripts/seed_patients.py

  # Stream vitals into the DB (and stdout), one reading per second
  python scripts/generate_vitals_stream.py

  # Custom interval and anomaly rate
  python scripts/generate_vitals_stream.py --interval 2.0 --anomaly-rate 0.2

  # Finite batch
  python scripts/generate_vitals_stream.py --max-readings 100

  # Also write JSON-lines to a file
  python scripts/generate_vitals_stream.py --output vitals.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import get_connection, init_db


ANOMALY_PROFILES = {
    "hypertensive_crisis": {
        "systolic_bp": (180, 220),
        "diastolic_bp": (110, 140),
        "heart_rate": (90, 130),
    },
    "bradycardia": {
        "heart_rate": (30, 50),
    },
    "tachycardia": {
        "heart_rate": (120, 180),
    },
    "hypoxemia": {
        "spo2": (82, 90),
        "respiratory_rate": (22, 35),
    },
    "fever": {
        "temperature": (101.0, 104.5),
        "heart_rate": (90, 120),
    },
    "sepsis_early": {
        "heart_rate": (95, 130),
        "temperature": (100.5, 103.5),
        "respiratory_rate": (22, 30),
        "systolic_bp": (85, 100),
        "spo2": (90, 95),
    },
}


@dataclass
class VitalBaseline:
    heart_rate: float = 75.0
    systolic_bp: float = 120.0
    diastolic_bp: float = 80.0
    spo2: float = 98.0
    temperature: float = 98.6
    respiratory_rate: float = 16.0


@dataclass
class PatientSimulator:
    patient_id: str = ""
    device_id: str = ""
    device_type: str = ""
    baseline: VitalBaseline = field(default_factory=VitalBaseline)
    _tick: int = 0
    _active_anomaly: str | None = None
    _anomaly_ticks_left: int = 0

    def __post_init__(self) -> None:
        self.baseline = VitalBaseline(
            heart_rate=random.gauss(75, 8),
            systolic_bp=random.gauss(120, 12),
            diastolic_bp=random.gauss(80, 8),
            spo2=min(100.0, random.gauss(97.5, 1.0)),
            temperature=random.gauss(98.6, 0.4),
            respiratory_rate=random.gauss(16, 2),
        )

    def _physiological_drift(self, base: float, amplitude: float, period: float) -> float:
        return base + amplitude * math.sin(2 * math.pi * self._tick / period)

    def _noisy(self, value: float, noise_std: float) -> float:
        return value + random.gauss(0, noise_std)

    def generate_reading(self, anomaly_rate: float) -> dict:
        self._tick += 1

        if self._anomaly_ticks_left > 0:
            self._anomaly_ticks_left -= 1
            if self._anomaly_ticks_left == 0:
                self._active_anomaly = None
        elif random.random() < anomaly_rate:
            self._active_anomaly = random.choice(list(ANOMALY_PROFILES.keys()))
            self._anomaly_ticks_left = random.randint(3, 12)

        hr = self._physiological_drift(self.baseline.heart_rate, 3.0, 60)
        sys_bp = self._physiological_drift(self.baseline.systolic_bp, 5.0, 90)
        dia_bp = self._physiological_drift(self.baseline.diastolic_bp, 3.0, 90)
        spo2 = self._physiological_drift(self.baseline.spo2, 0.5, 120)
        temp = self._physiological_drift(self.baseline.temperature, 0.2, 200)
        rr = self._physiological_drift(self.baseline.respiratory_rate, 1.0, 45)

        if self._active_anomaly:
            profile = ANOMALY_PROFILES[self._active_anomaly]
            progress = 1 - (self._anomaly_ticks_left / 12)
            blend = min(1.0, progress * 1.5)
            if "heart_rate" in profile:
                lo, hi = profile["heart_rate"]
                hr = hr * (1 - blend) + random.uniform(lo, hi) * blend
            if "systolic_bp" in profile:
                lo, hi = profile["systolic_bp"]
                sys_bp = sys_bp * (1 - blend) + random.uniform(lo, hi) * blend
            if "diastolic_bp" in profile:
                lo, hi = profile["diastolic_bp"]
                dia_bp = dia_bp * (1 - blend) + random.uniform(lo, hi) * blend
            if "spo2" in profile:
                lo, hi = profile["spo2"]
                spo2 = spo2 * (1 - blend) + random.uniform(lo, hi) * blend
            if "temperature" in profile:
                lo, hi = profile["temperature"]
                temp = temp * (1 - blend) + random.uniform(lo, hi) * blend
            if "respiratory_rate" in profile:
                lo, hi = profile["respiratory_rate"]
                rr = rr * (1 - blend) + random.uniform(lo, hi) * blend

        hr = self._noisy(hr, 1.5)
        sys_bp = self._noisy(sys_bp, 2.0)
        dia_bp = self._noisy(dia_bp, 1.5)
        spo2 = self._noisy(spo2, 0.3)
        temp = self._noisy(temp, 0.1)
        rr = self._noisy(rr, 0.5)

        spo2 = max(70.0, min(100.0, spo2))
        hr = max(20.0, min(250.0, hr))
        sys_bp = max(60.0, min(260.0, sys_bp))
        dia_bp = max(30.0, min(180.0, dia_bp))
        temp = max(90.0, min(110.0, temp))
        rr = max(4.0, min(60.0, rr))

        return {
            "reading_id": str(uuid.uuid4()),
            "patient_id": self.patient_id,
            "device_id": self.device_id,
            "device_type": self.device_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "heart_rate": round(hr, 1),
            "systolic_bp": round(sys_bp, 1),
            "diastolic_bp": round(dia_bp, 1),
            "spo2": round(spo2, 1),
            "temperature": round(temp, 1),
            "respiratory_rate": round(rr, 1),
            "anomaly": self._active_anomaly,
        }


def load_patients_from_db() -> list[PatientSimulator]:
    conn = get_connection()
    rows = conn.execute("SELECT id, device_id, device_type FROM patients ORDER BY last_name, first_name").fetchall()
    conn.close()

    if not rows:
        print("ERROR: No patients in the database. Run `python scripts/seed_patients.py` first.", file=sys.stderr)
        sys.exit(1)

    simulators = []
    for row in rows:
        sim = PatientSimulator(
            patient_id=row["id"],
            device_id=row["device_id"],
            device_type=row["device_type"],
        )
        simulators.append(sim)

    print(f"Loaded {len(simulators)} patients from database.", file=sys.stderr)
    return simulators


def write_reading_to_db(conn, reading: dict) -> None:
    conn.execute(
        """
        INSERT INTO vitals_readings (id, patient_id, timestamp, heart_rate, systolic_bp, diastolic_bp, spo2, temperature, respiratory_rate, anomaly, device_id, device_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reading["reading_id"],
            reading["patient_id"],
            reading["timestamp"],
            reading["heart_rate"],
            reading["systolic_bp"],
            reading["diastolic_bp"],
            reading["spo2"],
            reading["temperature"],
            reading["respiratory_rate"],
            reading["anomaly"],
            reading["device_id"],
            reading["device_type"],
        ),
    )


def reading_to_jsonl(reading: dict) -> dict:
    """Convert a flat reading to the JSON-lines output format."""
    return {
        "reading_id": reading["reading_id"],
        "patient_id": reading["patient_id"],
        "device_id": reading["device_id"],
        "device_type": reading["device_type"],
        "timestamp": reading["timestamp"],
        "vitals": {
            "heart_rate": {"value": reading["heart_rate"], "unit": "bpm"},
            "systolic_bp": {"value": reading["systolic_bp"], "unit": "mmHg"},
            "diastolic_bp": {"value": reading["diastolic_bp"], "unit": "mmHg"},
            "spo2": {"value": reading["spo2"], "unit": "%"},
            "temperature": {"value": reading["temperature"], "unit": "°F"},
            "respiratory_rate": {"value": reading["respiratory_rate"], "unit": "breaths/min"},
        },
        "anomaly": reading["anomaly"],
    }


def stream_vitals(
    *,
    interval: float,
    anomaly_rate: float,
    max_readings: int | None,
    output: TextIO | None,
    seed: int | None,
) -> None:
    if seed is not None:
        random.seed(seed)

    init_db()
    simulators = load_patients_from_db()
    conn = get_connection()
    total = 0

    try:
        while True:
            for sim in simulators:
                reading = sim.generate_reading(anomaly_rate)

                write_reading_to_db(conn, reading)

                if output:
                    output.write(json.dumps(reading_to_jsonl(reading)) + "\n")
                    output.flush()

                total += 1
                if max_readings and total >= max_readings:
                    conn.commit()
                    return

            conn.commit()

            if interval > 0:
                time.sleep(interval)
    except KeyboardInterrupt:
        conn.commit()
    finally:
        conn.close()

    print(f"\nWrote {total} readings to database.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic vitals data into the shared SQLite database."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between reading batches (default: 2.0, 0 for no delay)",
    )
    parser.add_argument(
        "--anomaly-rate",
        type=float,
        default=0.15,
        help="Probability of anomaly onset per reading (default: 0.15)",
    )
    parser.add_argument(
        "--max-readings",
        type=int,
        default=None,
        help="Stop after N total readings (default: unlimited)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Also write JSON-lines to this file (default: stdout only)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        default=False,
        help="Also emit JSON-lines to stdout",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducibility"
    )
    args = parser.parse_args()

    out: TextIO | None = None
    if args.stdout:
        out = sys.stdout
    elif args.output:
        out = open(args.output, "w")

    try:
        stream_vitals(
            interval=args.interval,
            anomaly_rate=args.anomaly_rate,
            max_readings=args.max_readings,
            output=out,
            seed=args.seed,
        )
    finally:
        if out and out is not sys.stdout:
            out.close()


if __name__ == "__main__":
    main()
