import { useParams, useNavigate } from "react-router-dom";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

const VITAL_CONFIG = {
  heart_rate: {
    label: "Heart Rate",
    unit: "bpm",
    color: "#ef4444",
    domain: [40, 180],
    thresholds: { low: 50, high: 110 },
  },
  systolic_bp: {
    label: "Systolic BP",
    unit: "mmHg",
    color: "#8b5cf6",
    domain: [60, 220],
    thresholds: { low: 90, high: 140 },
  },
  diastolic_bp: {
    label: "Diastolic BP",
    unit: "mmHg",
    color: "#a78bfa",
    domain: [30, 150],
    thresholds: { low: 60, high: 90 },
  },
  spo2: {
    label: "SpO2",
    unit: "%",
    color: "#3b82f6",
    domain: [80, 102],
    thresholds: { low: 93, high: 100 },
  },
  temperature: {
    label: "Temperature",
    unit: "°F",
    color: "#f59e0b",
    domain: [95, 106],
    thresholds: { low: 96.8, high: 100.4 },
  },
  respiratory_rate: {
    label: "Resp Rate",
    unit: "/min",
    color: "#10b981",
    domain: [4, 40],
    thresholds: { low: 12, high: 20 },
  },
};

function VitalChart({ vitalKey, history }) {
  const config = VITAL_CONFIG[vitalKey];
  const data = history.map((r, i) => ({
    tick: i,
    value: r.vitals[vitalKey].value,
    time: new Date(r.timestamp).toLocaleTimeString(),
  }));

  const latest = data[data.length - 1]?.value;
  const isAbnormal =
    latest !== undefined &&
    (latest < config.thresholds.low || latest > config.thresholds.high);

  return (
    <div className={`vital-chart-card ${isAbnormal ? "abnormal" : ""}`}>
      <div className="vital-chart-header">
        <div>
          <span className="vital-chart-label">{config.label}</span>
          <span className="vital-chart-unit">{config.unit}</span>
        </div>
        <span
          className="vital-chart-value"
          style={{ color: isAbnormal ? "#ef4444" : config.color }}
        >
          {latest ?? "--"}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 10, fill: "#64748b" }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={config.domain}
            tick={{ fontSize: 10, fill: "#64748b" }}
            width={35}
          />
          <Tooltip
            contentStyle={{
              background: "#0f172a",
              border: "1px solid #1e293b",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          <ReferenceLine
            y={config.thresholds.high}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            strokeOpacity={0.6}
          />
          <ReferenceLine
            y={config.thresholds.low}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            strokeOpacity={0.6}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={config.color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function AlertCard({ alert }) {
  const isCritical = alert.severity === "critical";
  const time = new Date(alert.timestamp).toLocaleTimeString();

  return (
    <div className={`alert-card ${alert.severity}`}>
      <div className="alert-card-header">
        <span className={`alert-severity-dot ${alert.severity}`} />
        <span className="alert-vital-name">
          {alert.vital === "sepsis_screen"
            ? "Sepsis Screening"
            : VITAL_CONFIG[alert.vital]?.label || alert.vital}
        </span>
        <span className="alert-time">{time}</span>
      </div>
      <div className="alert-value-row">
        <span className="alert-measured">
          Measured: <strong>{alert.value} {alert.unit}</strong>
        </span>
        {alert.vital !== "sepsis_screen" && (
          <span className="alert-threshold">
            Threshold: {alert.direction?.includes("high") ? ">" : "<"}{" "}
            {alert.threshold} {alert.unit}
          </span>
        )}
      </div>
      <p className="alert-description">{alert.description}</p>
    </div>
  );
}

export default function PatientDetail({ patients, vitalsHistory, alerts }) {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const patient = patients[patientId];
  const history = vitalsHistory[patientId] || [];
  const patientAlerts = (alerts[patientId] || []).slice().reverse();

  if (!patient) {
    return (
      <div className="patient-detail">
        <div className="detail-header">
          <button className="back-btn" onClick={() => navigate("/")}>
            ← Back
          </button>
          <h2>Patient not found</h2>
        </div>
      </div>
    );
  }

  const activeAlerts = patientAlerts.filter((a) => {
    const age = Date.now() - new Date(a.timestamp).getTime();
    return age < 30000;
  });

  return (
    <div className="patient-detail">
      <div className="detail-header">
        <button className="back-btn" onClick={() => navigate("/")}>
          ← Dashboard
        </button>
        <div className="detail-patient-info">
          <h2>{patient.name}</h2>
          <span className="detail-meta">
            {patient.age && `${patient.age} years`}
            {patient.room && ` · Room ${patient.room}`}
            {patient.device_type &&
              ` · ${patient.device_type.replace(/_/g, " ")}`}
          </span>
        </div>
        <span className={`status-badge large ${patient.status}`}>
          {patient.status?.toUpperCase()}
        </span>
      </div>

      {activeAlerts.length > 0 && (
        <div className="active-alerts-banner">
          <div className="banner-icon">⚠</div>
          <div className="banner-text">
            <strong>{activeAlerts.length} active alert{activeAlerts.length > 1 ? "s" : ""}</strong>
            {" — "}
            {activeAlerts
              .map(
                (a) =>
                  (a.vital === "sepsis_screen"
                    ? "Sepsis Screen"
                    : VITAL_CONFIG[a.vital]?.label || a.vital)
              )
              .filter((v, i, arr) => arr.indexOf(v) === i)
              .join(", ")}
          </div>
        </div>
      )}

      <div className="vitals-grid">
        {Object.keys(VITAL_CONFIG).map((key) => (
          <VitalChart key={key} vitalKey={key} history={history} />
        ))}
      </div>

      <div className="alerts-section">
        <h3>Alert History</h3>
        {patientAlerts.length === 0 ? (
          <p className="no-alerts">No alerts recorded for this patient.</p>
        ) : (
          <div className="alerts-list">
            {patientAlerts.slice(0, 30).map((alert) => (
              <AlertCard key={alert.id} alert={alert} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
