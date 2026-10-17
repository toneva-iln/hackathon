import { useEffect, useRef, useCallback, useState } from "react";

const WS_URL = "ws://localhost:8000/ws";
const RECONNECT_DELAY = 2000;

export function useVitalsStream() {
  const [patients, setPatients] = useState({});
  const [vitalsHistory, setVitalsHistory] = useState({});
  const [alerts, setAlerts] = useState({});
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type !== "vitals_update") return;

      const { patient_id, reading, alerts: newAlerts, status } = msg;

      setPatients((prev) => ({
        ...prev,
        [patient_id]: {
          ...prev[patient_id],
          patient_id,
          status,
          latest_vitals: reading,
          alert_count: newAlerts.length,
        },
      }));

      setVitalsHistory((prev) => {
        const history = prev[patient_id] || [];
        const updated = [...history, reading].slice(-120);
        return { ...prev, [patient_id]: updated };
      });

      if (newAlerts.length > 0) {
        setAlerts((prev) => {
          const existing = prev[patient_id] || [];
          const updated = [...existing, ...newAlerts].slice(-100);
          return { ...prev, [patient_id]: updated };
        });
      }
    };

    ws.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    fetch("http://localhost:8000/api/patients")
      .then((r) => r.json())
      .then((list) => {
        const map = {};
        list.forEach((p) => (map[p.patient_id] = p));
        setPatients(map);
      })
      .catch(() => {});

    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { patients, vitalsHistory, alerts, connected };
}
