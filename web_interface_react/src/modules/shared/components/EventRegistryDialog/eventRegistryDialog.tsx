import React from "react";
import axios from "axios";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";

interface Candidate { reason: string; score: number; event: { id: number; title: string; event_date: string | null } }
interface Kind { code: string; label: string }

interface Props {
  /** The name marked in the text (the "Nazwy wydarzeń" chip). */
  name: string;
  docId: string | number;
  apiUrl: string;
  headers: Record<string, string>;
  /** The event the name is linked to now: choosing another event replaces that link (it is removed first). */
  current?: { id: number; surface: string } | null;
  onClose: () => void;
  onDone: (message: string) => void;
}

/**
 * Promotes a named event marked in ONE document ("Nazwy wydarzeń" chip) to the registry of world events (ADR-034):
 * either the name is linked to an event that already exists (`POST /world_events/mentions/link`, only for this
 * document) or a new, confirmed event is created under a title the reviewer corrects here
 * (`POST /geo_events`, the marked name becomes its alias) and the name is linked to it. Nothing is written before
 * the button is pressed; a name alone never links anything.
 */
const EventRegistryDialog = ({ name, docId, apiUrl, headers, current, onClose, onDone }: Props) => {
  const [title, setTitle] = React.useState(name);
  const [kind, setKind] = React.useState("other");
  const [date, setDate] = React.useState("");
  const [kinds, setKinds] = React.useState<Kind[]>([]);
  const [candidates, setCandidates] = React.useState<Candidate[]>([]);
  const [target, setTarget] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const numericDocId = Number(docId);

  const lookup = React.useCallback(async (text: string) => {
    const query = text.trim();
    if (!query) { setCandidates([]); return; }
    try {
      const { data } = await axios.get<{ candidates: Candidate[] }>(
        `${apiUrl}/world_events/candidates`, { headers, params: { name: query } },
      );
      setCandidates(data.candidates ?? []);
      setTarget(null);
    } catch {
      setCandidates([]);
    }
  }, [apiUrl, headers]);

  React.useEffect(() => {
    axios.get<{ kinds: Kind[] }>(`${apiUrl}/geo_event_kinds`, { headers })
      .then(({ data }) => setKinds(data.kinds ?? []))
      .catch(() => setKinds([]));
    void lookup(name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const dateValid = date === "" || /^\d{4}(-\d{2}(-\d{2})?)?$/.test(date);
  const canSubmit = !busy && Number.isInteger(numericDocId) && dateValid && (target !== null || title.trim() !== "");

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const startedAt = Date.now();
    try {
      let eventId = target;
      let eventTitle = candidates.find((c) => c.event.id === target)?.event.title ?? title.trim();
      if (eventId === null) {
        const { data } = await axios.post<{ event: { id: number; title: string } }>(`${apiUrl}/geo_events`, {
          title: title.trim(), kind, aliases: [name], status: "confirmed", ...(date && { event_date: date }),
        }, { headers });
        eventId = data.event.id;
        eventTitle = data.event.title;
      }
      if (current && current.id !== eventId) {
        await axios.post(`${apiUrl}/world_events/mentions/unlink`,
          { name: current.surface, event_id: current.id, document_id: numericDocId }, { headers });
      }
      await axios.post(`${apiUrl}/world_events/mentions/link`,
        { name, event_id: eventId, document_ids: [numericDocId] }, { headers });
      onDone(`„${name}” jest teraz powiązane z wydarzeniem #${eventId} ${eventTitle}.`);
    } catch (err) {
      setError(describeRequestError(err, "Dodawanie wydarzenia do rejestru", {
        startedAt, context: { dokument: docId, nazwa: name },
      }));
      setBusy(false);
    }
  };

  return (
    <div role="dialog" aria-label={`Rejestr wydarzeń: ${name}`}
      style={{
        position: "fixed", left: "50%", top: 80, transform: "translateX(-50%)", zIndex: 1000, width: "min(560px, 92vw)",
        padding: 14, background: "#fff", border: "1px solid #94a3b8", borderRadius: 8, boxShadow: "0 6px 24px rgba(0,0,0,0.3)",
      }}>
      <strong>📅 {name}</strong>
      <p style={{ margin: "4px 0 8px", color: "#64748b", fontSize: "0.9em" }}>
        {current && <strong>Teraz powiązane z wydarzeniem #{current.id}. </strong>}
        Nazwa zaznaczona w tekście to jeszcze nie wydarzenie. Tu wiążesz ją z wydarzeniem z rejestru (<code>/world-events</code>)
        albo tworzysz nowe; powiązanie dotyczy tego dokumentu.
      </p>
      <label style={{ display: "block", marginBottom: 6 }}>
        Tytuł wydarzenia (rok i miejsce odróżniają edycje cyklicznych wydarzeń)
        <input type="text" value={title} disabled={target !== null} style={{ width: "100%", padding: "4px 6px", boxSizing: "border-box" }}
          onChange={(e) => setTitle(e.target.value)} onBlur={() => void lookup(title)} />
      </label>
      <div style={{ display: "flex", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
        <label>Rodzaj{" "}
          <select value={kind} disabled={target !== null} onChange={(e) => setKind(e.target.value)}>
            {kinds.length === 0 && <option value="other">inne</option>}
            {kinds.map((k) => <option key={k.code} value={k.code}>{k.label}</option>)}
          </select>
        </label>
        <label>Data (opcjonalnie){" "}
          <input type="text" value={date} placeholder="RRRR-MM-DD" disabled={target !== null} aria-invalid={!dateValid}
            style={{ width: 120 }} onChange={(e) => setDate(e.target.value.trim())} />
        </label>
      </div>
      {!dateValid && <p role="alert" style={{ color: "#a33", margin: "2px 0" }}>Data musi mieć postać RRRR, RRRR-MM albo RRRR-MM-DD.</p>}
      <button type="button" onClick={() => void lookup(title)} style={{ marginBottom: 6 }}>
        🔎 Sprawdź, czy już jest w rejestrze
      </button>
      {candidates.length > 0 && (
        <fieldset style={{ margin: "4px 0", border: "1px solid #e2e8f0" }}>
          <legend>Czy to to samo wydarzenie?</legend>
          <label style={{ display: "block" }}>
            <input type="radio" name="registry-target" checked={target === null} onChange={() => setTarget(null)} />
            {" "}Nie, utwórz nowe wydarzenie
          </label>
          {candidates.map((c) => (
            <label key={c.event.id} style={{ display: "block" }}>
              <input type="radio" name="registry-target" checked={target === c.event.id} onChange={() => setTarget(c.event.id)} />
              {" "}Tak, powiąż z: #{c.event.id} {c.event.title}
              <small style={{ color: "#64748b" }}>
                {" "}({c.event.event_date ?? "bez daty"}, {c.reason === "alias" ? "ta sama nazwa" : `podobna nazwa ${c.score}`})
              </small>
            </label>
          ))}
        </fieldset>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button type="button" disabled={!canSubmit} onClick={() => void submit()}>
          {busy ? "⏳ Zapisuję…" : target !== null ? "Powiąż z wydarzeniem" : "Utwórz wydarzenie i powiąż"}
        </button>
        <button type="button" disabled={busy} onClick={onClose}>Anuluj</button>
      </div>
      {error && (
        <div role="alert" style={{ color: "#a33" }}>
          <p>{error.summary}</p>
          <RequestErrorDetails details={error.details} />
        </div>
      )}
    </div>
  );
};

export default EventRegistryDialog;
