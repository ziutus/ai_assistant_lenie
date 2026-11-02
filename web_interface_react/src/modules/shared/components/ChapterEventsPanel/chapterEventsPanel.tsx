import React from "react";
import axios from "axios";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";

interface EventProposal {
  date_text: string;
  event_date: string | null;
  event_date_end: string | null;
  description: string;
  anchor_quote: string | null;
}

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
 * timeline. Nothing is turned into a named-event entity automatically.
 */
const ChapterEventsPanel = ({ apiUrl, apiKey, docId, position }: Props) => {
  const headers = React.useMemo(() => ({ "x-api-key": apiKey }), [apiKey]);
  const [open, setOpen] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [events, setEvents] = React.useState<EventProposal[] | null>(null);
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);

  // Proposals saved by an earlier run are loaded when the panel is opened for the first time.
  const load = async () => {
    try {
      const { data } = await axios.get<{ events: EventProposal[] }>(
        `${apiUrl}/document/${docId}/events`, { headers, params: { chapter_position: position } },
      );
      setEvents(data.events);
    } catch {
      setEvents([]);
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
        📅 Zdarzenia rozdziału{events && events.length > 0 ? ` (${events.length})` : ""}
      </button>
      {open && (
        <div style={{ marginTop: 6, paddingLeft: 8, borderLeft: "3px solid #fbcfe8" }}>
          <button type="button" disabled={busy} onClick={() => void detect()}
            title="Model szuka w tym rozdziale zdarzeń z datą; wynik zastępuje wcześniejsze propozycje tego rozdziału">
            {busy ? "⏳ Wykrywam zdarzenia…" : "🔎 Wykryj zdarzenia"}
          </button>
          {note && <p role="status" style={{ color: "#166534", margin: "4px 0" }}>{note}</p>}
          {error && (
            <div role="alert" style={{ color: "#a33" }}>
              <p>{error.summary}</p>
              <RequestErrorDetails details={error.details} />
            </div>
          )}
          {events !== null && events.length === 0 && !busy && (
            <small style={{ color: "#64748b" }}>Brak zapisanych propozycji zdarzeń dla tego rozdziału.</small>
          )}
          {events !== null && events.length > 0 && (
            <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
              {events.map((event, index) => (
                <li key={`${event.date_text}-${index}`} style={{ marginBottom: 4 }}>
                  <strong>{event.date_text}</strong>
                  {event.event_date && (
                    <small style={{ color: "#64748b" }}>
                      {" "}({event.event_date}{event.event_date_end ? ` – ${event.event_date_end}` : ""})
                    </small>
                  )}
                  {" — "}{event.description}
                  {event.anchor_quote && <div style={{ color: "#64748b", fontSize: "0.85em" }}>„{event.anchor_quote}”</div>}
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
