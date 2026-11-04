import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import SkillHint from "../SkillHint";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";

interface RegistryRef { id: number; title: string }

interface EventProposal {
  id?: number;
  world_events?: RegistryRef[];
  date_text: string;
  event_date: string | null;
  event_date_end: string | null;
  description: string;
  anchor_quote: string | null;
}

/** A registry event that cites this chapter's text without a timeline proposal behind it (the chapter skill). */
interface RegistrySource {
  id: number;
  anchor_quote: string;
  stance: string;
  event: { id: number; title: string; status: string; event_date: string | null };
}

const STATUS_LABEL: Record<string, string> = { confirmed: "zatwierdzone", proposed: "propozycja", rejected: "odrzucone" };

interface Candidate { reason: string; score: number; event: { id: number; title: string; event_date: string | null } }
interface Kind { code: string; label: string }

interface PromoteProps {
  apiUrl: string;
  headers: Record<string, string>;
  event: EventProposal;
  onDone: (registry: RegistryRef) => void;
  onCancel: () => void;
}

/**
 * Promotes ONE timeline proposal to the registry of world events (`POST /document_events/:id/to_world_event`,
 * ADR-034): either a new event under a title the reviewer corrects here (the transcript often spells names
 * wrongly) or one more source of an event that already exists. Nothing is written before "Dodaj".
 */
const PromoteForm = ({ apiUrl, headers, event, onDone, onCancel }: PromoteProps) => {
  const [title, setTitle] = React.useState(event.description);
  const [kind, setKind] = React.useState("other");
  const [kinds, setKinds] = React.useState<Kind[]>([]);
  const [candidates, setCandidates] = React.useState<Candidate[]>([]);
  const [target, setTarget] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);

  React.useEffect(() => {
    axios.get<{ kinds: Kind[] }>(`${apiUrl}/geo_event_kinds`, { headers })
      .then(({ data }) => setKinds(data.kinds ?? []))
      .catch(() => setKinds([]));
  }, [apiUrl, headers]);

  const lookup = async () => {
    const name = title.trim();
    if (!name) { setCandidates([]); return; }
    try {
      const { data } = await axios.get<{ candidates: Candidate[] }>(
        `${apiUrl}/world_events/candidates`, { headers, params: { name } },
      );
      setCandidates(data.candidates ?? []);
      setTarget(null);
    } catch {
      setCandidates([]);
    }
  };

  const canSubmit = !busy && event.id != null && (target !== null || title.trim() !== "");

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    const startedAt = Date.now();
    try {
      const body = target !== null ? { event_id: target } : { title: title.trim(), kind };
      const { data } = await axios.post<{ event: RegistryRef }>(
        `${apiUrl}/document_events/${event.id}/to_world_event`, body, { headers },
      );
      onDone({ id: data.event.id, title: data.event.title });
    } catch (err) {
      setError(describeRequestError(err, "Dodawanie zdarzenia do rejestru", {
        startedAt, context: { wpis: event.id },
      }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ margin: "4px 0 8px", padding: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#f8fafc" }}>
      <label style={{ display: "block", marginBottom: 6 }}>
        Tytuł zdarzenia (popraw pisownię z transkrypcji)
        <input type="text" value={title} disabled={target !== null} style={{ width: "100%", padding: "4px 6px" }}
          onChange={(e) => setTitle(e.target.value)} onBlur={() => void lookup()} />
      </label>
      <label style={{ display: "block", marginBottom: 6 }}>
        Rodzaj{" "}
        <select value={kind} disabled={target !== null} onChange={(e) => setKind(e.target.value)}>
          {kinds.length === 0 && <option value="other">inne</option>}
          {kinds.map((k) => <option key={k.code} value={k.code}>{k.label}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => void lookup()} style={{ marginBottom: 6 }}>
        🔎 Sprawdź, czy już jest w rejestrze
      </button>
      {candidates.length > 0 && (
        <fieldset style={{ margin: "4px 0", border: "1px solid #e2e8f0" }}>
          <legend>Czy to to samo zdarzenie?</legend>
          <label style={{ display: "block" }}>
            <input type="radio" name={`target-${event.id}`} checked={target === null} onChange={() => setTarget(null)} />
            {" "}Nie, utwórz nowe zdarzenie
          </label>
          {candidates.map((c) => (
            <label key={c.event.id} style={{ display: "block" }}>
              <input type="radio" name={`target-${event.id}`} checked={target === c.event.id}
                onChange={() => setTarget(c.event.id)} />
              {" "}Tak, dodaj jako źródło: #{c.event.id} {c.event.title}
              <small style={{ color: "#64748b" }}>
                {" "}({c.event.event_date ?? "bez daty"}, {c.reason === "alias" ? "ta sama nazwa" : `podobna nazwa ${c.score}`})
              </small>
            </label>
          ))}
        </fieldset>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" disabled={!canSubmit} onClick={() => void submit()}>
          {busy ? "⏳ Zapisuję…" : target !== null ? "Dodaj jako źródło" : "Dodaj do rejestru"}
        </button>
        <button type="button" disabled={busy} onClick={onCancel}>Anuluj</button>
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

interface Props {
  apiUrl: string;
  apiKey: string;
  docId: string | number;
  position: number;
}

/**
 * "Wykryj zdarzenia": the LLM looks for dated events in ONE chapter
 * (`POST /document/:id/chapter/:pos/detect_events`). The result is stored as proposals in `document_events`
 * (replacing the earlier proposals of this chapter only) and shown here; they also appear on the reader's
 * timeline. Nothing is turned into a named-event entity automatically; a proposal can be promoted by hand to the
 * registry of world events ("➕ Do zdarzeń globalnych", `PromoteForm`).
 */
const ChapterEventsPanel = ({ apiUrl, apiKey, docId, position }: Props) => {
  const headers = React.useMemo(() => ({ "x-api-key": apiKey }), [apiKey]);
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [events, setEvents] = React.useState<EventProposal[] | null>(null);
  const [registrySources, setRegistrySources] = React.useState<RegistrySource[]>([]);
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const [promoting, setPromoting] = React.useState<number | null>(null);

  const markPromoted = (eventId: number, registry: RegistryRef) => {
    setEvents((current) => (current ?? []).map((item) => (
      item.id === eventId ? { ...item, world_events: [...(item.world_events ?? []), registry] } : item
    )));
    setPromoting(null);
    setNote(`Dodano do rejestru zdarzeń: #${registry.id} ${registry.title}.`);
  };

  // Proposals saved by an earlier run are loaded when the panel is opened for the first time.
  const load = async () => {
    try {
      const { data } = await axios.get<{ events: EventProposal[]; registry_sources?: RegistrySource[] }>(
        `${apiUrl}/document/${docId}/events`, { headers, params: { chapter_position: position } },
      );
      setEvents(data.events);
      setRegistrySources(data.registry_sources ?? []);
    } catch {
      setEvents([]);
      setRegistrySources([]);
    }
  };

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && events === null) void load();
  };

  const detect = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNote("");
    const startedAt = Date.now();
    try {
      const { data } = await axios.post<{
        events: EventProposal[]; model: string; rejected_without_quote: number; rejected_without_date: number;
      }>(`${apiUrl}/document/${docId}/chapter/${position}/detect_events`, {}, { headers, timeout: 240000 });
      setEvents(data.events);
      const rejected = data.rejected_without_quote + data.rejected_without_date;
      setNote(`Model ${data.model}: ${data.events.length} zdarzeń`
        + (rejected > 0
          ? ` (odrzucone: ${data.rejected_without_quote} bez cytatu, ${data.rejected_without_date} bez daty)` : "")
        + ".");
    } catch (err) {
      setError(describeRequestError(err, `Wykrywanie zdarzeń w rozdziale ${position}`, {
        startedAt, context: { dokument: docId, rozdział: position },
      }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: 6 }}>
      <button type="button" onClick={toggle} aria-expanded={open}>
        📅 Zdarzenia rozdziału{events && events.length + registrySources.length > 0 ? ` (${events.length + registrySources.length})` : ""}
      </button>
      {open && (
        <div style={{ marginTop: 6, paddingLeft: 8, borderLeft: "3px solid #fbcfe8" }}>
          <button type="button" disabled={busy} onClick={() => void detect()}
            title="Model szuka w tym rozdziale zdarzeń z datą; wynik zastępuje wcześniejsze propozycje tego rozdziału">
            {busy ? "⏳ Wykrywam zdarzenia…" : "🔎 Wykryj zdarzenia"}
          </button>
          {" "}
          <SkillHint skill="/lenie-chapter-world-events" command={`/lenie-chapter-world-events ${docId} ${position}`}>
            Skill przejrzy zdarzenia tego rozdziału, sprawdzi duplikaty w rejestrze, dobierze rodzaj i kraje i po
            Twojej zgodzie doda je do zdarzeń globalnych.
          </SkillHint>
          {note && <p role="status" style={{ color: "#166534", margin: "4px 0" }}>{note}</p>}
          {error && (
            <div role="alert" style={{ color: "#a33" }}>
              <p>{error.summary}</p>
              <RequestErrorDetails details={error.details} />
            </div>
          )}
          {events !== null && events.length === 0 && registrySources.length === 0 && !busy && (
            <small style={{ color: "#64748b" }}>Brak zapisanych propozycji zdarzeń dla tego rozdziału.</small>
          )}
          {registrySources.length > 0 && (
            <div aria-label="Zdarzenia z rejestru cytujące ten rozdział" style={{ margin: "6px 0" }}>
              <strong style={{ fontSize: "0.9em" }}>W rejestrze zdarzeń ({registrySources.length})</strong>
              <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
                {registrySources.map((source) => (
                  <li key={source.id} style={{ marginBottom: 4 }}>
                    <span style={{ color: "#166534" }}>✓ </span>
                    <Link to={`/world-events?q=${encodeURIComponent(source.event.title)}`}>#{source.event.id} {source.event.title}</Link>
                    <small style={{ color: "#64748b" }}>
                      {" "}({source.event.event_date ?? "bez daty"}, {STATUS_LABEL[source.event.status] ?? source.event.status}
                      {source.stance === "disputes" ? ", przeczy" : ""})
                    </small>
                    <div style={{ color: "#64748b", fontSize: "0.85em" }}>„{source.anchor_quote}”</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {events !== null && events.length > 0 && (
            <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
              {events.map((event, index) => (
                <li key={event.id ?? `${event.date_text}-${index}`} style={{ marginBottom: 4 }}>
                  <strong>{event.date_text}</strong>
                  {event.event_date && (
                    <small style={{ color: "#64748b" }}>
                      {" "}({event.event_date}{event.event_date_end ? ` – ${event.event_date_end}` : ""})
                    </small>
                  )}
                  {" — "}{event.description}
                  {event.anchor_quote && <div style={{ color: "#64748b", fontSize: "0.85em" }}>„{event.anchor_quote}”</div>}
                  {(event.world_events ?? []).map((registry) => (
                    <div key={registry.id} style={{ fontSize: "0.85em", color: "#166534" }}>
                      ✓ W rejestrze zdarzeń:{" "}
                      <Link to={`/world-events?q=${encodeURIComponent(registry.title)}`}>#{registry.id} {registry.title}</Link>
                    </div>
                  ))}
                  {event.id != null && promoting !== event.id && (
                    <button type="button" onClick={() => setPromoting(event.id ?? null)}
                      title="Zapisuje to zdarzenie w globalnym rejestrze zdarzeń świata (/world-events)">
                      {(event.world_events ?? []).length > 0 ? "➕ Dodaj do kolejnego zdarzenia" : "➕ Do zdarzeń globalnych"}
                    </button>
                  )}
                  {event.id != null && promoting === event.id && (
                    <PromoteForm apiUrl={apiUrl} headers={headers} event={event}
                      onDone={(registry) => markPromoted(event.id as number, registry)}
                      onCancel={() => setPromoting(null)} />
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default ChapterEventsPanel;
