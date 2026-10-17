# Vitals Streaming Platform

Real-time patient vitals monitoring platform with live anomaly detection. Simulates blood pressure cuffs, pulse oximeters, wearables, and multiparameter monitors streaming continuous vital signs through a shared SQLite database, consumed by a FastAPI backend and pushed to a React dashboard via WebSocket.

## Quick Start (Local Dev)

```bash
# 1. Install Python dependencies
pip install -r api/requirements.txt

# 2. Run database migration
alembic upgrade head

# 3. Seed patients
python scripts/seed_patients.py

# 4. Start the vitals generator (writes to DB every 2 seconds)
python scripts/generate_vitals_stream.py &

# 5. Start the API (reads from DB, pushes to frontend via WebSocket)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Start the frontend (separate terminal, from hackathon/frontend/)
npm install
npm run dev
```

Open http://localhost:5173 — the dashboard connects automatically, no page refresh needed.

## Quick Start (Docker — Production)

```bash
docker compose up --build
```

This starts three services:

1. **generator** — seeds the patients table (first run only), then streams vitals into the shared `data/vitals.db`
2. **api** — reads from the database, detects anomalies, broadcasts via WebSocket on port 8000
3. **frontend** — dashboard on port 3000 (nginx reverse proxy to the API)

Open http://localhost:3000.

## Quick Start (Docker — Development / Hot Reload)

```bash
docker compose -f docker-compose.dev.yml up --build
```

Same ports, but source code is mounted as volumes so changes are picked up automatically — no rebuild needed:

- **API** — uvicorn runs with `--reload`, watches `api/main.py` and `db/`
- **Frontend** — Vite dev server with HMR, watches `frontend/src/`
- **Generator** — scripts and db modules are mounted in; restart the container to pick up changes (`docker compose -f docker-compose.dev.yml restart generator`)

Open http://localhost:3000.

## Architecture

```
hackathon/
├── docker-compose.yml                # Production (nginx + built assets)
├── docker-compose.dev.yml            # Development (hot reload)
├── alembic.ini                       # Alembic config (points at data/vitals.db)
├── data/
│   └── vitals.db                     # Shared SQLite database (gitignored)
├── db/
│   ├── __init__.py
│   ├── database.py                   # DB connection helpers + raw schema init
│   ├── models.py                     # SQLAlchemy ORM models (Patient, VitalsReading)
│   └── migrations/                   # Alembic migrations
│       └── versions/
├── api/
│   ├── Dockerfile
│   ├── main.py                       # FastAPI — polls DB, detects anomalies, WebSocket
│   └── requirements.txt
├── frontend/
│   ├── Dockerfile                    # Multi-stage: Node build → nginx
│   ├── nginx.conf                    # Proxies /api and /ws to API container
│   └── src/
│       ├── App.jsx                   # Router (Dashboard + Patient Detail)
│       ├── hooks/
│       │   └── useVitalsStream.js    # WebSocket hook — real-time state
│       └── components/
│           ├── Dashboard.jsx         # Patient list with alert badges
│           └── PatientDetail.jsx     # Live charts + alert history
└── scripts/
    ├── Dockerfile                    # Generator container (seeds + streams)
    ├── seed_patients.py              # Seeds patients table with 12 RPM patients
    └── generate_vitals_stream.py     # Reads patients from DB, writes vitals to DB
```

## Data Flow

```
seed_patients.py → [patients table]
                        ↓
generate_vitals_stream.py → [vitals_readings table]
                                     ↓
                              api/main.py (polls DB every 1s)
                                     ↓
                              WebSocket broadcast
                                     ↓
                              React dashboard (live updates)
```

Both the generator and the API read patients from the same `patients` table, so IDs and names are always aligned.

## Database

SQLite with WAL mode, stored at `data/vitals.db`. Managed by Alembic migrations.

### Patients table

| Column | Type | Description |
|---|---|---|
| id | TEXT PK | UUID |
| first_name | TEXT | Patient first name |
| last_name | TEXT | Patient last name |
| date_of_birth | TEXT | ISO date (YYYY-MM-DD) |
| sex | TEXT | M or F |
| room | TEXT | Ward-room (e.g. B-400) |
| primary_diagnosis | TEXT | Reason for RPM enrollment |
| admission_date | TEXT | ISO date |
| device_id | TEXT | Assigned device ID |
| device_type | TEXT | Device model |
| created_at | TEXT | Auto-populated |

### Vitals Readings table

| Column | Type | Description |
|---|---|---|
| id | TEXT PK | UUID per reading |
| patient_id | TEXT FK | References patients.id |
| timestamp | TEXT | ISO timestamp (UTC) |
| heart_rate | REAL | bpm |
| systolic_bp | REAL | mmHg |
| diastolic_bp | REAL | mmHg |
| spo2 | REAL | % |
| temperature | REAL | °F |
| respiratory_rate | REAL | breaths/min |
| anomaly | TEXT | Anomaly profile name or NULL |
| device_id | TEXT | Device that produced the reading |
| device_type | TEXT | Device model |

### ORM Models

`db/models.py` defines SQLAlchemy models `Patient` and `VitalsReading` that mirror these tables.

### Migrations

```bash
# Run pending migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "description"
```

## Features

- **Shared database** — generator and API both use the same SQLite `patients` table; no ID drift
- **Real-time streaming** — API polls DB for new readings every second, pushes via WebSocket
- **Live anomaly detection** — threshold-based alerts for all 6 vitals + sepsis screening (SIRS criteria)
- **Dashboard** — patient cards in stable positions with pulsing alert badges and live vital pills
- **Patient detail** — 6 live-updating Recharts line charts with threshold reference lines, active alert banner, full alert history with clinical descriptions
- **Auto-reconnect** — WebSocket reconnects on disconnect with visual indicator
- **Dockerized** — single `docker compose up` runs the generator, API, and frontend behind an nginx reverse proxy

## Anomaly Detection

Threshold-based detection with two severity levels:

| Vital | Warning | Critical |
|---|---|---|
| Heart Rate | <50 or >110 bpm | <40 or >150 bpm |
| Systolic BP | <90 or >140 mmHg | <80 or >180 mmHg |
| Diastolic BP | <60 or >90 mmHg | <50 or >120 mmHg |
| SpO2 | <93% | <88% |
| Temperature | <96.8 or >100.4°F | <95.0 or >103.0°F |
| Resp Rate | <12 or >20/min | <8 or >30/min |

**Sepsis screening:** triggers when 3+ SIRS criteria are met simultaneously (HR >90, temp abnormal, RR >20, systolic BP <100).


## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/patients` | All patients with current status + alert count |
| GET | `/api/patients/{id}` | Patient detail + latest vitals + active/historical alerts |
| GET | `/api/patients/{id}/vitals` | Last 300 vitals readings |
| GET | `/api/patients/{id}/alerts` | Active + historical alerts |
| WS | `/ws` | Real-time vitals + alert stream |

## Synthetic Data Generator

`scripts/generate_vitals_stream.py` reads patients from the database and writes vitals readings back.

```bash
# Default: all patients, 2s interval, 15% anomaly rate
python scripts/generate_vitals_stream.py

# Also emit JSON-lines to stdout
python scripts/generate_vitals_stream.py --stdout

# Finite batch
python scripts/generate_vitals_stream.py --max-readings 100

# Custom anomaly rate
python scripts/generate_vitals_stream.py --anomaly-rate 0.3
```

Six anomaly profiles: `hypertensive_crisis`, `bradycardia`, `tachycardia`, `hypoxemia`, `fever`, `sepsis_early`. See `--help` for all options.

## Why This Matters — The Clinical Case for Real-Time RPM

### The problem

Every year, millions of patients are discharged from hospitals with chronic conditions — heart failure, COPD, post-cardiac surgery, hypertension — and sent home with a Bluetooth blood pressure cuff and a pulse oximeter. The data these devices produce either lands in a spreadsheet someone checks once a day, or it generates so many raw threshold alerts that clinical staff learns to ignore them. Patients deteriorate at home, unnoticed, and end up back in the emergency room.

A single preventable readmission costs the hospital system approximately $15,000. CMS penalizes hospitals for excess 30-day readmissions. The gap is not a lack of data — it's a lack of a real-time clinical lens on that data.

### Who this is for

The primary user is a **care coordinator or RPM nurse** at a hospital system's Remote Patient Monitoring program, responsible for a panel of **30–50 patients recovering at home**. This is not a bedside ICU monitor replacement — those patients already have million-dollar Philips and GE systems with built-in alarms. This platform serves the patients who fall through the cracks *after* they leave the hospital.

### Clinical use cases

| Scenario | What the platform catches | Why it matters |
|---|---|---|
| **Post-cardiac surgery discharge** | Hypertensive crisis (BP >180/110) or dropping SpO2 in the hours after the patient gets home | Intervene before the patient calls 911 — a phone call and med adjustment vs. an ER visit |
| **Heart failure management** | Rising BP + tachycardia pattern over several readings, suggesting fluid retention | Early diuretic adjustment prevents acute decompensation and hospitalization |
| **COPD exacerbation detection** | SpO2 trending downward + rising respiratory rate over hours — not a single bad reading, but a trajectory | The trend is the signal; a single low reading could be sensor noise |
| **Sepsis-risk post-discharge** | 3+ SIRS criteria met simultaneously (elevated HR, abnormal temp, tachypnea, hypotension) | Patients at home cannot self-assess for sepsis; the platform's screening catches what they would miss |
| **Medication titration monitoring** | Bradycardia or hypotension emerging after a beta-blocker dose increase | Catch adverse drug effects before they become symptomatic emergencies |

### From reactive to proactive

Without this platform, the care model is reactive: the patient feels bad, calls 911, arrives at the ER, and the hospital absorbs the cost and readmission penalty. With it, the RPM nurse sees a trend forming on the dashboard, calls the patient, coordinates with the prescribing physician, and adjusts the care plan — all before the patient knows something is wrong.

This is the difference between **surveillance** and **intelligence**. The devices generate the data. This platform makes it actionable.

### Revenue model

Remote Patient Monitoring is directly reimbursable by CMS under CPT codes 99453–99458, covering device setup, patient education, and ongoing monitoring time. Hospitals with RPM programs also reduce 30-day readmission rates, avoiding CMS penalties under the Hospital Readmissions Reduction Program (HRRP). The platform pays for itself through avoided readmissions and generates net-new revenue through RPM billing.

## Glossary

| Term | Definition |
|---|---|
| **Atrial fibrillation (AFib)** | An irregular, often rapid heart rhythm originating in the upper chambers (atria) of the heart. Increases stroke risk. |
| **Bradycardia** | Abnormally slow heart rate, typically below 60 bpm at rest. Can indicate heart block, medication side effects, or hypothyroidism. |
| **Bradypnea** | Abnormally slow respiratory rate, typically below 12 breaths per minute. May indicate CNS depression or opioid overdose. |
| **CABG** | Coronary Artery Bypass Grafting — open-heart surgery that reroutes blood around blocked coronary arteries. Patients require close post-surgical monitoring. |
| **CMS** | Centers for Medicare & Medicaid Services — the U.S. federal agency that administers Medicare and Medicaid. Sets reimbursement rules for RPM programs. |
| **COPD** | Chronic Obstructive Pulmonary Disease — a group of progressive lung diseases (emphysema, chronic bronchitis) that cause airflow obstruction and breathing difficulty. |
| **CPT codes (99453–99458)** | Current Procedural Terminology billing codes used to reimburse Remote Patient Monitoring services: device setup, patient education, data collection, and clinical review time. |
| **Diastolic blood pressure** | The lower number in a blood pressure reading (e.g. the 80 in 120/80). Measures the pressure in arteries when the heart rests between beats. Normal range: 60–90 mmHg. |
| **DVT** | Deep Vein Thrombosis — a blood clot forming in a deep vein, usually in the leg. A risk after surgery or prolonged immobility. Can be life-threatening if the clot travels to the lungs (pulmonary embolism). |
| **Heart rate (HR)** | The number of times the heart beats per minute (bpm). Normal resting range for adults: 60–100 bpm. |
| **HRRP** | Hospital Readmissions Reduction Program — a CMS program that penalizes hospitals with excess 30-day readmission rates for certain conditions. |
| **Hyperpyrexia** | Extremely high fever, typically above 103°F (39.4°C). A medical emergency with risk of organ damage. |
| **Hypertension** | Persistently elevated blood pressure (systolic >140 or diastolic >90 mmHg). A major risk factor for stroke, heart attack, and kidney disease. |
| **Hypertensive crisis** | A severe, acute elevation in blood pressure (systolic >180 and/or diastolic >120 mmHg). Requires immediate medical intervention to prevent organ damage. |
| **Hypotension** | Abnormally low blood pressure (systolic <90 mmHg). Can cause dizziness, fainting, and in severe cases, shock and organ failure. |
| **Hypothermia** | Body temperature below 95°F (35°C). Can cause cardiac arrhythmia, confusion, and organ failure. |
| **Hypoxemia** | Abnormally low oxygen level in the blood, typically SpO2 below 90%. Indicates respiratory compromise requiring supplemental oxygen. |
| **mmHg** | Millimeters of mercury — the standard unit for measuring blood pressure. |
| **Pulse oximeter** | A non-invasive device, typically clipped to a fingertip, that measures SpO2 and heart rate by shining light through the skin to detect oxygen levels in hemoglobin. |
| **Respiratory rate (RR)** | The number of breaths a person takes per minute. Normal adult range: 12–20 breaths/min. |
| **RPM** | Remote Patient Monitoring — the practice of using connected devices (BP cuffs, pulse oximeters, scales) to track a patient's vitals from their home, reviewed remotely by clinical staff. |
| **Sepsis** | A life-threatening organ dysfunction caused by the body's dysregulated response to infection. Early detection is critical — mortality increases ~8% for every hour treatment is delayed. |
| **SIRS criteria** | Systemic Inflammatory Response Syndrome — a set of clinical signs used to screen for sepsis: (1) HR >90 bpm, (2) temperature >100.4°F or <96.8°F, (3) respiratory rate >20/min, (4) WBC count abnormal. Meeting 2+ criteria with suspected infection suggests sepsis. This platform checks the first four non-lab criteria. |
| **SpO2** | Peripheral capillary oxygen saturation — the percentage of hemoglobin in the blood that is carrying oxygen, measured by a pulse oximeter. Normal range: 95–100%. |
| **Systolic blood pressure** | The upper number in a blood pressure reading (e.g. the 120 in 120/80). Measures the peak pressure in arteries when the heart contracts. Normal range: 90–140 mmHg. |
| **Tachycardia** | Abnormally fast heart rate, typically above 100 bpm at rest. Can indicate stress, fever, dehydration, arrhythmia, or early sepsis. |
| **Tachypnea** | Abnormally rapid respiratory rate, typically above 20 breaths per minute. May indicate respiratory distress, pain, metabolic acidosis, or sepsis. |
| **WAL mode** | Write-Ahead Logging — a SQLite journaling mode that allows concurrent reads and writes. Used in this platform so the generator can write while the API reads simultaneously. |
