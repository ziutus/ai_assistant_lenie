import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";

type Dependency = {
  id: string;
  name: string;
  status: "ok" | "warning" | "down" | "unknown";
  observed_only: boolean;
  successes: number;
  failures: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error_code: string | null;
  last_operation?: string | null;
};

type Report = { observed_at: string; window_minutes: number; services: Dependency[] };

const STATUS_STYLE: Record<Dependency["status"], { label: string; color: string; background: string }> = {
  ok: { label: "Działa", color: "#166534", background: "#dcfce7" },
  warning: { label: "Ostrzeżenie", color: "#92400e", background: "#fef3c7" },
  down: { label: "Niedostępna", color: "#b91c1c", background: "#fee2e2" },
  unknown: { label: "Brak obserwacji", color: "#475569", background: "#e2e8f0" },
};

const WINDOWS: { minutes: number; label: string }[] = [
  { minutes: 15, label: "15 minut" }, { minutes: 60, label: "1 godzina" }, { minutes: 24 * 60, label: "24 godziny" },
  { minutes: 7 * 24 * 60, label: "7 dni" }, { minutes: 30 * 24 * 60, label: "30 dni" },
];

const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
// dateStyle/timeStyle cannot be combined with timeZoneName (or any other
// component option) -- Intl.DateTimeFormat throws a TypeError at
// construction time, which crashed this whole page (uncaught render
// exception, no error boundary -- looked like the app was hanging). The
// local timezone is already shown once in the page intro, so it doesn't
// need repeating on every timestamp.
const stamp = (value: string | null) => value
  ? new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium", timeStyle: "medium",
    }).format(new Date(value))
  : "—";

const ServiceStatus = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [report, setReport] = React.useState<Report | null>(null);
  const [error, setError] = React.useState("");
  const [windowMinutes, setWindowMinutes] = React.useState(15);

  const load = React.useCallback(async () => {
    try {
      const response = await axios.get(`${apiUrl}/service_status`, {
        headers: { "x-api-key": apiKey ?? "" },
        params: { window_minutes: windowMinutes },
      });
      setReport(response.data);
      setError("");
    } catch (cause: any) {
      setError(cause.response?.data?.message ?? "Nie udało się pobrać statusu usług");
    }
  }, [apiKey, apiUrl, windowMinutes]);

  React.useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  return <div>
    <h2>Status usług zewnętrznych</h2>
    <p style={{ color: "#475569" }}>
      Status bazuje na rzeczywistych wywołaniach usług (LLM, embeddingi, Webshare, napisy YouTube) z wybranego okna; nie wykonuje płatnych zapytań kontrolnych. Czasy są lokalne ({localTimezone}).
    </p>
    <label>Okno <select value={windowMinutes} onChange={(event) => setWindowMinutes(Number(event.target.value))}>
      {WINDOWS.map((option) => <option key={option.minutes} value={option.minutes}>{option.label}</option>)}
    </select></label>
    <button className="button" style={{ marginLeft: 12 }} onClick={() => void load()}>Odśwież</button>
    {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
    {report?.services.map(service => {
      const style = STATUS_STYLE[service.status];
      return <section key={service.id} style={{ marginTop: 14, padding: 16, border: "1px solid #cbd5e1", borderRadius: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <strong>{service.name}</strong>
          <span style={{ padding: "4px 8px", borderRadius: 999, color: style.color, background: style.background }}>{style.label}</span>
        </div>
        <p>{service.successes} udanych / {service.failures} nieudanych wywołań w ostatnich {WINDOWS.find((option) => option.minutes === report.window_minutes)?.label ?? `${report.window_minutes} min`}.</p>
        <div style={{ color: "#475569", fontSize: "0.9em" }}>
          Ostatni sukces: {stamp(service.last_success_at)}<br/>
          Ostatni błąd: {stamp(service.last_failure_at)}{service.last_error_code ? ` (${service.last_error_code})` : ""}
          {service.last_operation ? <><br/>Ostatnia akcja: {service.last_operation}</> : null}
        </div>
      </section>;
    })}
    {report && <p style={{ color: "#64748b", fontSize: "0.85em" }}>Odczyt: {stamp(report.observed_at)}. „Brak obserwacji” nie oznacza awarii — w tym oknie nie było wywołań.</p>}
  </div>;
};

export default ServiceStatus;
