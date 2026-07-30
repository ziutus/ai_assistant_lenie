import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

type Job = { id: string; status: string; created_at?: string | null; finished_at?: string | null; error?: string | null };
type Schedule = {
  id: string; job_type: string; enabled: boolean; description: string; timezone: string;
  times: string[]; schedule: string; next_run_at?: string | null; last_job?: Job | null;
};
type SchedulerResponse = { generated_at: string; schedules: Schedule[] };

const REFRESH_INTERVAL_MS = 30_000;
const formatDate = (value?: string | null) => value ? new Date(value).toLocaleString("pl-PL") : "—";
const statusColor: Record<string, string> = { done: "#15803d", failed: "#b91c1c", running: "#1d4ed8", queued: "#475569", cancelled: "#475569" };

function ScheduleCard({ schedule, onSave }: { schedule: Schedule; onSave: (body: Pick<Schedule, "enabled" | "timezone" | "times">) => Promise<void> }) {
  const [enabled, setEnabled] = React.useState(schedule.enabled);
  const [timezone, setTimezone] = React.useState(schedule.timezone);
  const [times, setTimes] = React.useState(schedule.times.join(", "));
  const [saving, setSaving] = React.useState(false);
  const save = async () => {
    setSaving(true);
    try { await onSave({ enabled, timezone, times: times.split(",").map((value) => value.trim()).filter(Boolean) }); }
    finally { setSaving(false); }
  };
  return <article style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: 16 }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
      <div><h3 style={{ margin: 0 }}>{schedule.job_type}</h3><p style={{ margin: "6px 0" }}>{schedule.description}</p></div>
      <span style={{ color: schedule.enabled ? "#15803d" : "#64748b", fontWeight: 700 }}>{schedule.enabled ? "Włączony" : "Wyłączony"}</span>
    </div>
    <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "7px 12px", margin: "14px 0 0" }}>
      <dt>Harmonogram</dt><dd style={{ margin: 0 }}>{schedule.schedule}</dd>
      <dt>Strefa</dt><dd style={{ margin: 0 }}>{schedule.timezone}</dd>
      <dt>Następne uruchomienie</dt><dd style={{ margin: 0 }}>{schedule.enabled ? formatDate(schedule.next_run_at) : "—"}</dd>
      <dt>Ostatni job</dt><dd style={{ margin: 0 }}>{schedule.last_job ? <><span style={{ color: statusColor[schedule.last_job.status] || "#475569", fontWeight: 700 }}>{schedule.last_job.status}</span> · {formatDate(schedule.last_job.finished_at || schedule.last_job.created_at)}</> : "Brak"}</dd>
    </dl>
    <fieldset style={{ marginTop: 16, border: 0, padding: 0 }}>
      <legend style={{ fontWeight: 700 }}>Edycja harmonogramu</legend>
      <label style={{ display: "block", marginTop: 8 }}><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Włączony</label>
      <label style={{ display: "block", marginTop: 8 }}>Godziny (HH:MM, oddzielone przecinkami) <input value={times} onChange={(event) => setTimes(event.target.value)} /></label>
      <label style={{ display: "block", marginTop: 8 }}>Strefa czasowa <input value={timezone} onChange={(event) => setTimezone(event.target.value)} /></label>
      <button type="button" className="button" style={{ marginTop: 10 }} disabled={saving} onClick={() => void save()}>{saving ? "Zapisuję…" : "Zapisz"}</button>
    </fieldset>
    {schedule.last_job?.error && <p className="errorText" style={{ marginBottom: 0 }}>Ostatni błąd: {schedule.last_job.error}</p>}
  </article>;
}

export default function Scheduler() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [data, setData] = React.useState<SchedulerResponse | null>(null);
  const [error, setError] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/scheduler`, { headers: { "x-api-key": apiKey || "" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setData(await response.json());
      setError("");
    } catch (cause) {
      setError(`Nie udało się pobrać stanu schedulera (${cause instanceof Error ? cause.message : "błąd połączenia"}).`);
    }
  }, [apiKey, apiUrl]);

  const save = React.useCallback(async (id: string, body: Pick<Schedule, "enabled" | "timezone" | "times">) => {
    try {
      const response = await fetch(`${apiUrl}/scheduler/${id}`, { method: "PATCH", headers: { "x-api-key": apiKey || "", "content-type": "application/json" }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await load();
    } catch (cause) {
      setError(`Nie udało się zapisać harmonogramu (${cause instanceof Error ? cause.message : "błąd połączenia"}).`);
    }
  }, [apiKey, apiUrl, load]);

  React.useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  return <section>
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
      <h2 style={{ margin: 0 }}>Scheduler</h2>
      <button type="button" className="button" onClick={() => void load()}>Odśwież</button>
    </div>
    <p style={{ color: "#475569" }}>Planowane zadania są tworzone przez workera. Widok odświeża się co 30 sekund.</p>
    {error && <p className="errorText" role="alert">{error}</p>}
    {!data && !error && <p>Ładowanie…</p>}
    {data && <>
      <p style={{ color: "#475569", fontSize: ".9em" }}>Stan z: {formatDate(data.generated_at)}</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
        {data.schedules.map((schedule) => <ScheduleCard key={schedule.id} schedule={schedule} onSave={(body) => save(schedule.id, body)} />)}
      </div>
    </>}
  </section>;
}
