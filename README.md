# Vitals Streaming Platform

Real-time patient vitals monitoring platform with live anomaly detection. Simulates blood pressure cuffs, pulse oximeters, wearables, and multiparameter monitors streaming continuous vital signs through a FastAPI backend to a React dashboard via WebSocket.

## Quick Start (Docker)

```bash
docker compose up --build
```

Open http://localhost:3000 — the dashboard connects automatically, no page refresh needed.

The nginx proxy handles API and WebSocket routing to the backend container.

## Quick Start (Local Dev)

```bash
# Terminal 1 — API (from hackathon/)
pip install -r api/requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (from hackathon/frontend/)
npm install
npm run dev
```

Open http://localhost:5173 in local dev mode.

## Architecture

```
hackathon/
├── docker-compose.yml            # Runs API + frontend containers
├── api/
│   ├── Dockerfile
│   ├── main.py                   # FastAPI app — simulation, anomaly detection, WebSocket
│   └── requirements.txt
├── frontend/
│   ├── Dockerfile                # Multi-stage: Node build → nginx
│   ├── nginx.conf                # Proxies /api and /ws to the API container
│   ├── .env.development          # Points at localhost:8000 for local dev
│   ├── .env.production           # Empty — uses relative URLs through nginx
│   └── src/
│       ├── App.jsx               # Router (Dashboard + Patient Detail)
│       ├── hooks/
│       │   └── useVitalsStream.js    # WebSocket hook — real-time state
│       └── components/
│           ├── Dashboard.jsx         # Patient list with alert badges
│           └── PatientDetail.jsx     # Live charts + alert history
└── scripts/
    └── generate_vitals_stream.py     # Standalone CLI data generator
```

## Features

- **Real-time streaming** — WebSocket pushes vitals every 2 seconds, no polling
- **Live anomaly detection** — threshold-based alerts for all 6 vitals + sepsis screening (SIRS criteria)
- **Dashboard** — patient cards in stable positions with pulsing alert badges and live vital pills
- **Patient detail** — 6 live-updating Recharts line charts with threshold reference lines, active alert banner, full alert history with clinical descriptions
- **Auto-reconnect** — WebSocket reconnects on disconnect with visual indicator
- **Dockerized** — single `docker compose up` runs everything behind an nginx reverse proxy

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

## Synthetic Data Generator (Standalone)

`scripts/generate_vitals_stream.py` produces JSON-lines output independently of the API.

```bash
python scripts/generate_vitals_stream.py --patients 10 --max-readings 1000 --output vitals.jsonl
python scripts/generate_vitals_stream.py --seed 42 --max-readings 50
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
