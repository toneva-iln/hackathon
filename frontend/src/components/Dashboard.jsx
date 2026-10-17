import { useNavigate } from "react-router-dom";

const STATUS_CONFIG = {
  critical: { color: "#ef4444", bg: "#fef2f2", label: "CRITICAL", pulse: true },
  warning: { color: "#f59e0b", bg: "#fffbeb", label: "WARNING", pulse: true },
  stable: { color: "#10b981", bg: "#ecfdf5", label: "STABLE", pulse: false },
};

function VitalPill({ label, value, unit }) {
  return (
    <span className="vital-pill">
      <span className="vital-pill-label">{label}</span>
      <span className="vital-pill-value">{value}</span>
      <span className="vital-pill-unit">{unit}</span>
    </span>
  );
}

function PatientCard({ patient }) {
  const navigate = useNavigate();
  const status = STATUS_CONFIG[patient.status] || STATUS_CONFIG.stable;
  const vitals = patient.latest_vitals?.vitals;

  return (
    <div
      className={`patient-card ${patient.status}`}
      onClick={() => navigate(`/patient/${patient.patient_id}`)}
    >
      <div className="patient-card-header">
        <div className="patient-identity">
          <h3 className="patient-name">{patient.name}</h3>
          <span className="patient-meta">
            {patient.age && `${patient.age}y`}
            {patient.room && ` · Room ${patient.room}`}
          </span>
        </div>
        <div className="patient-badges">
          {patient.alert_count > 0 && (
            <span
              className={`alert-badge ${status.pulse ? "pulse" : ""}`}
              style={{ backgroundColor: status.color }}
            >
              {patient.alert_count}
            </span>
          )}
          <span
            className="status-badge"
            style={{ color: status.color, backgroundColor: status.bg }}
          >
            {status.label}
          </span>
        </div>
      </div>

      {vitals && (
        <div className="patient-vitals-row">
          <VitalPill label="HR" value={vitals.heart_rate.value} unit="bpm" />
          <VitalPill
            label="BP"
            value={`${vitals.systolic_bp.value}/${vitals.diastolic_bp.value}`}
            unit="mmHg"
          />
          <VitalPill label="SpO2" value={vitals.spo2.value} unit="%" />
          <VitalPill label="Temp" value={vitals.temperature.value} unit="°F" />
          <VitalPill label="RR" value={vitals.respiratory_rate.value} unit="/min" />
        </div>
      )}

      <div className="patient-device">
        {patient.device_type?.replace(/_/g, " ")}
        {patient.device_id && ` · ${patient.device_id}`}
      </div>
    </div>
  );
}

export default function Dashboard({ patients, connected }) {
  const patientList = Object.values(patients);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <h1>Vitals Monitor</h1>
          <span className="patient-count">{patientList.length} patients</span>
        </div>
        <div className="header-right">
          <span className={`connection-dot ${connected ? "online" : "offline"}`} />
          <span className="connection-label">
            {connected ? "Live" : "Reconnecting..."}
          </span>
        </div>
      </header>

      <div className="stats-bar">
        <div className="stat-item critical">
          <span className="stat-value">
            {patientList.filter((p) => p.status === "critical").length}
          </span>
          <span className="stat-label">Critical</span>
        </div>
        <div className="stat-item warning">
          <span className="stat-value">
            {patientList.filter((p) => p.status === "warning").length}
          </span>
          <span className="stat-label">Warning</span>
        </div>
        <div className="stat-item stable">
          <span className="stat-value">
            {patientList.filter((p) => p.status === "stable").length}
          </span>
          <span className="stat-label">Stable</span>
        </div>
      </div>

      <div className="patient-grid">
        {patientList.map((p) => (
          <PatientCard key={p.patient_id} patient={p} />
        ))}
      </div>
    </div>
  );
}
