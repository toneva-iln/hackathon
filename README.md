# Vitals Streaming Platform

Real-time patient vitals monitoring platform with live anomaly detection. Simulates blood pressure cuffs, pulse oximeters, wearables, and multiparameter monitors streaming continuous vital signs through a FastAPI backend to a React dashboard via WebSocket.

## Quick Start

```bash
# Terminal 1 — API (from hackathon/)
pip install -r api/requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (from hackathon/frontend/)
npm install
npm run dev
```

Open http://localhost:5173 — the dashboard connects automatically, no page refresh needed.

## Architecture

```
hackathon/
├── api/
│   ├── main.py              # FastAPI app — simulation, anomaly detection, WebSocket
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx           # Router (Dashboard + Patient Detail)
│       ├── hooks/
│       │   └── useVitalsStream.js   # WebSocket hook — real-time state
│       └── components/
│           ├── Dashboard.jsx         # Patient list with alert badges
│           └── PatientDetail.jsx     # Live charts + alert history
└── scripts/
    └── generate_vitals_stream.py    # Standalone CLI data generator
```

## Features

- **Real-time streaming** — WebSocket pushes vitals every 2 seconds, no polling
- **Live anomaly detection** — threshold-based alerts for all 6 vitals + sepsis screening (SIRS criteria)
- **Dashboard** — patient list sorted by severity, pulsing alert badges, live vital pills
- **Patient detail** — 6 live-updating Recharts line charts with threshold reference lines, active alert banner, full alert history with clinical descriptions
- **Auto-reconnect** — WebSocket reconnects on disconnect with visual indicator

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
