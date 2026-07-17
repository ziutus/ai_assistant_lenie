import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";

export type EventDatePrecision = "day" | "month" | "year" | "decade" | "century" | "era" | "unknown";

export interface EventItem {
  date_text: string;
  event_date: string | null;
  event_date_end: string | null;
  date_precision: EventDatePrecision;
  sort_year: number | null;
  description: string;
  anchor_quote: string | null;
  chapter_position: number | null;
}

interface TimelinePanelProps {
  docId?: string;
  currentChapter: number;
  onEventClick: (event: EventItem) => void;
}

const COARSE_PRECISION_LABELS: Partial<Record<EventDatePrecision, string>> = {
  decade: "dekada",
  century: "wiek",
  era: "okres historyczny",
};

const TimelinePanel: React.FC<TimelinePanelProps> = ({ docId, currentChapter, onEventClick }) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [isOpen, setIsOpen] = React.useState(false);
  const [scopeChapter, setScopeChapter] = React.useState(true);
  const [events, setEvents] = React.useState<EventItem[] | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const requestId = React.useRef(0);

  React.useEffect(() => {
    requestId.current += 1;
    setIsOpen(false);
    setScopeChapter(true);
    setEvents(null);
    setLoading(false);
    setError(null);
  }, [docId]);

  const loadEvents = React.useCallback(async () => {
    if (!docId || events !== null || loading) return;
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/document/${docId}/events`, {
        headers: { "x-api-key": apiKey ?? "" },
      });
      const data = await response.json();
      if (!response.ok || (!Array.isArray(data) && data.status && data.status !== "success")) {
        throw new Error(data.message ?? "Nie udało się pobrać osi czasu");
      }
      if (currentRequest === requestId.current) {
        setEvents((Array.isArray(data) ? data : data.events ?? []) as EventItem[]);
      }
    } catch (fetchError) {
      if (currentRequest === requestId.current) setError(String(fetchError));
    } finally {
      if (currentRequest === requestId.current) setLoading(false);
    }
  }, [apiUrl, apiKey, docId, events, loading]);

  // chapter_position == null means the document has no chapters — such events
  // belong to the whole document and must survive the default chapter scope
  const shownEvents = React.useMemo(
    () => (events ?? []).filter(event =>
      !scopeChapter || event.chapter_position == null || event.chapter_position === currentChapter),
    [events, scopeChapter, currentChapter],
  );

  const groupedEvents = React.useMemo(() => {
    const groups: { year: number | null; events: EventItem[] }[] = [];
    shownEvents.forEach(event => {
      const previous = groups[groups.length - 1];
      if (!previous || previous.year !== event.sort_year) {
        groups.push({ year: event.sort_year, events: [event] });
      } else {
        previous.events.push(event);
      }
    });
    return groups;
  }, [shownEvents]);

  return (
    <details
      open={isOpen}
      onToggle={event => {
        const open = event.currentTarget.open;
        setIsOpen(open);
        if (open) void loadEvents();
      }}
      style={{
        background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
        padding: 10, marginTop: 12,
      }}
    >
      <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 700 }}>
        🕰️ Oś czasu{events ? ` (${events.length})` : ""}
      </summary>

      <div style={{ fontSize: "0.78em", color: "#64748b", display: "flex", gap: 8, marginTop: 10 }}>
        Zakres:
        {([["bieżący rozdział", true], ["cały dokument", false]] as const).map(([label, value]) => (
          <button
            key={label}
            type="button"
            onClick={() => setScopeChapter(value)}
            style={{
              border: "none", background: "none", cursor: "pointer", padding: 0,
              color: scopeChapter === value ? "#0369a1" : "#94a3b8",
              fontWeight: scopeChapter === value ? 600 : undefined,
              textDecoration: scopeChapter === value ? undefined : "underline",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <div style={{ color: "#64748b", fontSize: "0.82em", marginTop: 10 }}>Ładowanie osi czasu…</div>}
      {error && (
        <div style={{ color: "#b91c1c", fontSize: "0.82em", marginTop: 10 }}>
          {error}{" "}
          <button type="button" onClick={() => void loadEvents()}>Spróbuj ponownie</button>
        </div>
      )}
      {!loading && !error && events !== null && shownEvents.length === 0 && (
        <div style={{ color: "#94a3b8", fontSize: "0.82em", marginTop: 10 }}>
          {scopeChapter ? "Brak wydarzeń w tym rozdziale." : "Brak wydarzeń w dokumencie."}
        </div>
      )}

      {groupedEvents.map(group => (
        <div key={group.year ?? "unknown"} style={{ marginTop: 12 }}>
          <div style={{
            color: "#475569", fontSize: "0.76em", fontWeight: 700,
            borderBottom: "1px solid #e2e8f0", paddingBottom: 3,
          }}>
            {group.year ?? "Bez ustalonego roku"}
          </div>
          {group.events.map((event, index) => {
            const precisionLabel = COARSE_PRECISION_LABELS[event.date_precision];
            return (
              <button
                key={`${event.chapter_position}-${event.date_text}-${index}`}
                type="button"
                onClick={() => onEventClick(event)}
                title={event.anchor_quote ?? undefined}
                style={{
                  display: "block", width: "100%", textAlign: "left", cursor: "pointer",
                  border: "none", borderBottom: "1px solid #f1f5f9", background: "transparent",
                  padding: "8px 2px", color: "inherit",
                }}
              >
                <span style={{ color: "#0369a1", fontSize: "0.78em", fontWeight: 700 }}>
                  {event.date_text}
                </span>
                {precisionLabel && (
                  <span style={{ color: "#94a3b8", fontSize: "0.7em", marginLeft: 6 }}>
                    ({precisionLabel})
                  </span>
                )}
                <span style={{ display: "block", fontSize: "0.82em", lineHeight: 1.4, marginTop: 2 }}>
                  {event.description}
                </span>
                {event.chapter_position != null && (
                  <span style={{ color: "#94a3b8", fontSize: "0.68em" }}>rozdz. {event.chapter_position}</span>
                )}
              </button>
            );
          })}
        </div>
      ))}
    </details>
  );
};

export default TimelinePanel;
