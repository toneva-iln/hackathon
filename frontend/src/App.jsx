import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useVitalsStream } from "./hooks/useVitalsStream";
import Dashboard from "./components/Dashboard";
import PatientDetail from "./components/PatientDetail";

export default function App() {
  const { patients, vitalsHistory, alerts, connected } = useVitalsStream();

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={<Dashboard patients={patients} connected={connected} />}
        />
        <Route
          path="/patient/:patientId"
          element={
            <PatientDetail
              patients={patients}
              vitalsHistory={vitalsHistory}
              alerts={alerts}
            />
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
