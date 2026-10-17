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
