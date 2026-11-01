import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";

// One registry event (ADR-034): dates, kind, names (aliases), participants of three kinds, the documents that
// talk about it. The card owns its small writes and asks the page to reload afterwards.

export interface Kind { code: string; label: string }
export interface Role { code: string; label: string }
export interface CountryRef { id: number; slug: string; name_pl: string }
export interface Participant {
  type: "country" | "organization" | "person";
  role: string;
  country?: CountryRef;
  organization?: { id: number; name: string };
  person?: { id: number; name: string };
}
export interface WorldEvent {
  id: number; title: string; description: string | null; kind: string;
  event_date: string | null; date_precision: string; event_date_end: string | null; end_date_precision: string | null;
  is_ongoing: boolean; status: string; version: number;
  detection_method?: string; model?: string | null; prompt_version?: string | null;
  aliases: { id: number; alias: string }[];
  participants: Participant[];
  source_count?: number; document_count?: number; mention_names?: string[];
  documents?: { id: number; title: string | null; via: string }[];
}

export const STATUS_LABEL: Record<string, string> = { proposed: "propozycja", confirmed: "zatwierdzone", rejected: "odrzucone" };
const TYPE_LABEL: Record<string, string> = { country: "kraj", organization: "organizacja", person: "osoba" };

export const errorText = (reason: any): string => {
  const data = reason?.response?.data?.message;
  if (data) return data;
  if (reason?.response) return `serwer odpowiedział błędem ${reason.response.status}`;
  if (reason?.request || reason?.message === "Network Error") return "brak odpowiedzi serwera; sprawdź logi backendu";
  return reason?.message || "nieznany błąd";
};

export const formatDates = (event: Pick<WorldEvent, "event_date" | "event_date_end" | "is_ongoing">): string => {
  if (!event.event_date) return "bez daty";
  if (event.event_date_end) return `${event.event_date} – ${event.event_date_end}`;
  return event.is_ongoing ? `${event.event_date} – trwa` : event.event_date;
};

export const participantName = (p: Participant): string =>
  p.country?.name_pl ?? p.organization?.name ?? p.person?.name ?? "?";

const participantId = (p: Participant): number => (p.country ?? p.organization ?? p.person)!.id;

interface Props {
  event: WorldEvent;
  kinds: Kind[];
  roles: Role[];
  countries: CountryRef[];
  apiUrl: string;
  headers: Record<string, string>;
  onChanged: () => void;
  onMessage: (message: string, isError?: boolean) => void;
}

const WorldEventCard = ({ event, kinds, roles, countries, apiUrl, headers, onChanged, onMessage }: Props) => {
  const [editing, setEditing] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [form, setForm] = React.useState({
    title: event.title, description: event.description ?? "", kind: event.kind, event_date: event.event_date ?? "",
    event_date_end: event.event_date_end ?? "", is_ongoing: event.is_ongoing,
  });
  const [alias, setAlias] = React.useState("");
  const [participant, setParticipant] = React.useState({ type: "country", ref: "", role: "location" });
  const kindLabel = kinds.find((k) => k.code === event.kind)?.label ?? event.kind;
  const url = `${apiUrl}/geo_events/${event.id}`;

  const run = async (action: () => Promise<unknown>, success?: string) => {
    setBusy(true);
    try {
      await action();
      if (success) onMessage(success);
      onChanged();
    } catch (reason: any) {
      onMessage(reason?.response?.status === 409 && /changed since/.test(errorText(reason))
        ? "Ktoś zmienił to zdarzenie w międzyczasie; odświeżam. Spróbuj ponownie."
        : `Nie udało się zapisać: ${errorText(reason)}`, true);
      if (reason?.response?.status === 409) onChanged();
    } finally {
      setBusy(false);
    }
  };

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    const changes: Record<string, unknown> = {};
    if (form.title !== event.title) changes.title = form.title;
    if (form.description !== (event.description ?? "")) changes.description = form.description;
    if (form.kind !== event.kind) changes.kind = form.kind;
    if (form.event_date !== (event.event_date ?? "")) changes.event_date = form.event_date;
    if (form.event_date_end !== (event.event_date_end ?? "")) changes.event_date_end = form.event_date_end;
    if (form.is_ongoing !== event.is_ongoing) changes.is_ongoing = form.is_ongoing;
    if (Object.keys(changes).length === 0) { setEditing(false); return; }
    void run(async () => {
      await axios.patch(url, { ...changes, expected_version: event.version }, { headers });
      setEditing(false);
    }, "Zapisano zdarzenie.");
  };

  const addParticipant = (e: React.FormEvent) => {
    e.preventDefault();
    const raw = participant.ref.trim();
    if (!raw) return;
    const ref = participant.type !== "country" && /^\d+$/.test(raw) ? Number(raw) : raw;
    void run(async () => {
      await axios.post(`${url}/participants`, { type: participant.type, ref, role: participant.role }, { headers });
      setParticipant({ ...participant, ref: "" });
    });
  };

  const rolesFor = participant.type === "person" ? roles.filter((r) => r.code !== "location") : roles;

  return (
    <li style={{ padding: "8px 10px", marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
      <div>
        <strong>{event.title}</strong>{" "}
        <span style={{ color: "#64748b", fontSize: "0.85em" }}>
          {kindLabel} · {formatDates(event)} · {STATUS_LABEL[event.status] ?? event.status}
          {event.detection_method === "llm" ? ` · ${event.model ?? "model"}${event.prompt_version ? `, prompt ${event.prompt_version}` : ""}` : ""}
        </span>
      </div>
      {event.description && <div style={{ margin: "4px 0" }}>{event.description}</div>}

      <div style={{ fontSize: "0.9em", margin: "4px 0" }} aria-label="Uczestnicy">
        {event.participants.length === 0
          ? <span style={{ color: "#94a3b8" }}>Bez uczestników (kraj nie jest wymagany).</span>
          : event.participants.map((p) => (
            <span key={`${p.type}-${participantId(p)}-${p.role}`}
              style={{ display: "inline-block", margin: "0 6px 4px 0", padding: "1px 8px", borderRadius: 10, background: "#f1f5f9" }}
              title={TYPE_LABEL[p.type]}>
              {p.type === "organization" ? "🏢 " : p.type === "person" ? "👤 " : "🌍 "}
              {participantName(p)} ({roles.find((r) => r.code === p.role)?.label ?? p.role})
              <button type="button" aria-label={`Usuń uczestnika ${participantName(p)}`} disabled={busy}
                style={{ border: 0, background: "none", cursor: "pointer", color: "#94a3b8" }}
                onClick={() => run(() => axios.delete(`${url}/participants`, { headers, data: { type: p.type, id: participantId(p), role: p.role } }))}>×</button>
            </span>
          ))}
      </div>

      <div style={{ fontSize: "0.85em", margin: "4px 0" }} aria-label="Nazwy">
        <span style={{ color: "#64748b" }}>Nazwy: </span>
        {event.aliases.map((a) => (
          <span key={a.id} style={{ marginRight: 8 }}>
            {a.alias}
            {a.alias !== event.title && (
              <button type="button" aria-label={`Usuń nazwę ${a.alias}`} disabled={busy}
                style={{ border: 0, background: "none", cursor: "pointer", color: "#94a3b8" }}
                onClick={() => run(() => axios.delete(`${url}/aliases/${a.id}`, { headers }))}>×</button>
            )}
          </span>
        ))}
      </div>

      {(event.documents?.length ?? 0) > 0 && (
        <div style={{ fontSize: "0.85em", margin: "4px 0" }} aria-label="Dokumenty">
          <span style={{ color: "#64748b" }}>Dokumenty ({event.document_count}): </span>
          {event.documents!.map((d) => (
            <Link key={d.id} to={`/read/${d.id}`} style={{ marginRight: 10 }}>
              {d.title || `Dokument ${d.id}`}{d.via === "mention" ? " ⟲" : ""}
            </Link>
          ))}
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
        {event.status === "proposed" && <>
          <button type="button" className="button" disabled={busy}
            onClick={() => run(() => axios.patch(url, { status: "confirmed" }, { headers }))}>Zatwierdź</button>
          <button type="button" className="button" disabled={busy}
            onClick={() => run(() => axios.patch(url, { status: "rejected" }, { headers }))}>Odrzuć</button>
        </>}
        <button type="button" className="button" onClick={() => setEditing(!editing)}>{editing ? "Zamknij edycję" : "Edytuj"}</button>
      </div>

      {editing && (
        <div style={{ marginTop: 8, padding: 8, background: "#f8fafc", borderRadius: 6 }}>
          <form onSubmit={save} aria-label="Edycja zdarzenia" style={{ display: "grid", gap: 6 }}>
            <label>Nazwa <input aria-label="Nazwa zdarzenia" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} style={{ width: "100%" }} /></label>
            <label>Rodzaj{" "}
              <select aria-label="Rodzaj" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {kinds.map((k) => <option key={k.code} value={k.code}>{k.label}</option>)}
              </select>
            </label>
            <label>Początek <input aria-label="Data początku" placeholder="RRRR-MM-DD, RRRR-MM, RRRR albo puste" value={form.event_date} onChange={(e) => setForm({ ...form, event_date: e.target.value })} /></label>
            <label>Koniec <input aria-label="Data końca" placeholder="puste = brak" value={form.event_date_end} disabled={form.is_ongoing} onChange={(e) => setForm({ ...form, event_date_end: e.target.value })} /></label>
            <label><input type="checkbox" aria-label="Trwa nadal" checked={form.is_ongoing} onChange={(e) => setForm({ ...form, is_ongoing: e.target.checked, event_date_end: e.target.checked ? "" : form.event_date_end })} /> trwa nadal (koniec nieznany)</label>
            <label>Opis <textarea aria-label="Opis zdarzenia" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={{ width: "100%" }} /></label>
            <div><button type="submit" className="button" disabled={busy}>Zapisz</button></div>
          </form>

          <form onSubmit={(e) => { e.preventDefault(); if (alias.trim()) void run(async () => { await axios.post(`${url}/aliases`, { alias }, { headers }); setAlias(""); }); }}
            aria-label="Dodaj nazwę" style={{ display: "flex", gap: 6, marginTop: 8 }}>
            <input aria-label="Nowa nazwa" placeholder="inna nazwa tego zdarzenia" value={alias} onChange={(e) => setAlias(e.target.value)} />
            <button type="submit" className="button" disabled={busy}>Dodaj nazwę</button>
          </form>

          <form onSubmit={addParticipant} aria-label="Dodaj uczestnika" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            <select aria-label="Typ uczestnika" value={participant.type}
              onChange={(e) => setParticipant({ type: e.target.value, ref: "", role: e.target.value === "person" ? "subject" : "location" })}>
              {Object.entries(TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            {participant.type === "country"
              ? <select aria-label="Kraj uczestnika" value={participant.ref} onChange={(e) => setParticipant({ ...participant, ref: e.target.value })}>
                <option value="">— kraj —</option>
                {countries.map((c) => <option key={c.id} value={c.slug}>{c.name_pl}</option>)}
              </select>
              : <input aria-label="Uczestnik (id lub dokładna nazwa)" placeholder="id lub dokładna nazwa z rejestru" value={participant.ref}
                onChange={(e) => setParticipant({ ...participant, ref: e.target.value })} />}
            <select aria-label="Rola uczestnika" value={participant.role} onChange={(e) => setParticipant({ ...participant, role: e.target.value })}>
              {rolesFor.map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
            </select>
            <button type="submit" className="button" disabled={busy}>Dodaj uczestnika</button>
          </form>
        </div>
      )}
    </li>
  );
};

export default WorldEventCard;
