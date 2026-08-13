import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";

type Dependency = {
  id: string;
  name: string;
  status: "ok" | "warning" | "down" | "unknown";
  successes: number;
  failures: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error_code: string | null;
  last_operation?: string | null;
};

type Report = { observed_at: string; window_minutes: number; services: Dependency[] };

const STYLES: Record<Dependency["status"], { label: string; color: string; background: string }> = {
  ok: { label: "Działa", color: "#166534", background: "#dcfce7" },
  warning: { label: "Ostrzeżenie", color: "#92400e", background: "#fef3c7" },
  down: { label: "Niedostępna", color: "#b91c1c", background: "#fee2e2" },
  unknown: { label: "Brak obserwacji", color: "#475569", background: "#e2e8f0" },
};

const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const stamp = (value: string | null) => value
  ? new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium", timeStyle: "medium", timeZoneName: "short",
    }).format(new Date(value))
  : "—";

const ServiceStatus = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [report, setReport] = React.useState<Report | null>(null);
  const [error, setError] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      const response = await axios.get(`${apiUrl}/service_status`, {
        headers: { "x-api-key": apiKey ?? "" },
      });
      setReport(response.data);
      setError("");
    } catch (cause: any) {
      setError(cause.response?.data?.message ?? "Nie udało się pobrać statusu usług");
    }
  }, [apiKey, apiUrl]);

  React.useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  return <div>
    <h2>Status usług zewnętrznych</h2>
    <p style={{ color: "#475569" }}>
      Status bazuje na rzeczywistych wywołaniach LLM i embeddingów z ostatnich 15 minut; nie wykonuje płatnych zapytań kontrolnych. Czasy są lokalne ({localTimezone}).
    </p>
    <button className="button" onClick={() => void load()}>Odśwież</button>
    {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
    {report?.services.map(service => {
      const style = STYLES[service.status];
      return <section key={service.id} style={{ marginTop: 14, padding: 16, border: "1px solid #cbd5e1", borderRadius: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <strong>{service.name}</strong>
          <span style={{ padding: "4px 8px", borderRadius: 999, color: style.color, background: style.background }}>{style.label}</span>
        </div>
        <p>{service.successes} udanych / {service.failures} nieudanych wywołań w ostatnich {report.window_minutes} min.</p>
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
