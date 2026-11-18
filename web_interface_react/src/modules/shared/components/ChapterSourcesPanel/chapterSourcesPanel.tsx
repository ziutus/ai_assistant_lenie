import React from "react";
import axios from "axios";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";
import { SOURCE_ROLES, SOURCE_TYPES, sourceRoleLabel, sourceTypeLabel } from "./sourceOptions";

/** One link between the document and an information source (`GET /document/:id/information_sources`). */
export interface DocumentSourceEntry {
  id: number;
  source_id: number;
  canonical_name: string;
  source_type: string | null;
  organization_id: number | null;
  role: string;
  evidence_excerpt: string | null;
  review_status: string;
  extraction_method: string;
}

/** Letters and digits only, so a quote matches its chapter whatever the quotation marks, dashes and spacing. */
export const looseText = (value: string): string => value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();

/**
 * The sources a chapter shows: not an organization (those are the "Źródła cytowane" chips), not the publishing portal,
 * and whose stored quote occurs in the chapter text.
 */
export const sourcesOfChapter = (entries: DocumentSourceEntry[], chapterText: string): DocumentSourceEntry[] => {
  const haystack = looseText(chapterText);
  return entries.filter((entry) => {
    if (entry.organization_id != null || entry.role === "publisher" || entry.review_status === "rejected") return false;
    const quote = looseText(entry.evidence_excerpt ?? "");
    return quote !== "" && haystack.includes(quote);
  });
};

interface Props {
  apiUrl: string;
  apiKey: string;
  docId: string | number;
  /** Text of the chapter (its sentences joined): decides which of the document's sources belong here. */
  chapterText: string;
  /** Bump to reload (e.g. after a timeline entry was turned into a source). */
  refreshKey?: number;
}

interface EditFormProps {
  entry: DocumentSourceEntry;
  busy: boolean;
  onSave: (body: { name: string; source_type: string; role: string }) => void;
  onCancel: () => void;
}

const EditForm = ({ entry, busy, onSave, onCancel }: EditFormProps) => {
  const [name, setName] = React.useState(entry.canonical_name);
  const [sourceType, setSourceType] = React.useState(entry.source_type ?? "other");
  const [role, setRole] = React.useState(entry.role);
  return (
    <div style={{ margin: "4px 0 8px", padding: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#f8fafc" }}>
      <label style={{ display: "block", marginBottom: 6 }}>
        Nazwa źródła (autorzy i/lub tytuł)
        <input type="text" value={name} maxLength={200} style={{ width: "100%", padding: "4px 6px" }}
          onChange={(event) => setName(event.target.value)} />
      </label>
      <label style={{ display: "block", marginBottom: 6 }}>
        Rodzaj źródła{" "}
        <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
          {SOURCE_TYPES.map((type) => <option key={type.code} value={type.code}>{type.label}</option>)}
        </select>
      </label>
      <label style={{ display: "block", marginBottom: 6 }}>
        Rola w dokumencie{" "}
        <select value={role} onChange={(event) => setRole(event.target.value)}>
          {SOURCE_ROLES.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
        </select>
      </label>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" disabled={busy || name.trim() === ""}
          onClick={() => onSave({ name: name.trim(), source_type: sourceType, role })}>
          {busy ? "⏳ Zapisuję…" : "Zapisz"}
        </button>
        <button type="button" disabled={busy} onClick={onCancel}>Anuluj</button>
      </div>
    </div>
  );
};

/**
 * "Źródła informacji" of a chapter on `/ner/:id`: publications and other sources the extractors found for the
 * document (a study, a book, a report) that are NOT organizations from the text, so they have no chip. Each can be
 * approved, renamed/retyped or rejected (`PATCH /document/:id/information_sources/:linkId`); a rejected one is
 * remembered, so a new detection does not propose it again. Nothing is drawn when the chapter has none.
 */
const ChapterSourcesPanel = ({ apiUrl, apiKey, docId, chapterText, refreshKey = 0 }: Props) => {
  const headers = React.useMemo(() => ({ "x-api-key": apiKey }), [apiKey]);
  const [entries, setEntries] = React.useState<DocumentSourceEntry[]>([]);
  const [editing, setEditing] = React.useState<number | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);

  const load = React.useCallback(async () => {
    try {
      const { data } = await axios.get<{ entries?: DocumentSourceEntry[] }>(
        `${apiUrl}/document/${docId}/information_sources`, { headers },
      );
      setEntries(Array.isArray(data?.entries) ? data.entries : []);
    } catch {
      setEntries([]);
    }
  }, [apiUrl, docId, headers]);

  React.useEffect(() => { void load(); }, [load, refreshKey]);

  const update = async (entry: DocumentSourceEntry, body: Record<string, string>, done: string, action: string) => {
    setBusy(true);
    setError(null);
    const startedAt = Date.now();
    try {
      await axios.patch(`${apiUrl}/document/${docId}/information_sources/${entry.id}`, body, { headers });
      setEditing(null);
      setNote(done);
      await load();
    } catch (err) {
      setError(describeRequestError(err, action, { startedAt, context: { źródło: entry.id } }));
    } finally {
      setBusy(false);
    }
  };

  const shown = sourcesOfChapter(entries, chapterText);
  if (shown.length === 0 && !note) return null;

  return (
    <div aria-label="Źródła informacji rozdziału" style={{ marginTop: 6 }}>
      <strong>Źródła informacji{shown.length > 0 ? ` (${shown.length})` : ""}:</strong>
      <div style={{ marginTop: 6, paddingLeft: 8, borderLeft: "3px solid #bfdbfe" }}>
        {note && <p role="status" style={{ color: "#166534", margin: "4px 0" }}>{note}</p>}
        {error && (
          <div role="alert" style={{ color: "#a33" }}>
            <p>{error.summary}</p>
            <RequestErrorDetails details={error.details} />
          </div>
        )}
        <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
          {shown.map((entry) => (
            <li key={entry.id} style={{ marginBottom: 6 }}>
              <strong>{entry.canonical_name}</strong>
              <small style={{ color: "#64748b" }}>
                {" "}({sourceTypeLabel(entry.source_type)}, {sourceRoleLabel(entry.role)})
              </small>
              {entry.review_status === "needs_review" && (
                <span title="Źródło wykryte automatycznie; zatwierdź je albo odrzuć"
                  style={{ marginLeft: 6, padding: "0 6px", borderRadius: 3, background: "#fef3c7", fontSize: "0.85em" }}>
                  do potwierdzenia
                </span>
              )}
              {entry.evidence_excerpt && (
                <div style={{ color: "#64748b", fontSize: "0.85em" }}>„{entry.evidence_excerpt}”</div>
              )}
              {editing !== entry.id && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 2 }}>
                  {entry.review_status !== "approved" && (
                    <button type="button" disabled={busy}
                      onClick={() => void update(entry, { review_status: "approved" },
                        `Zatwierdzono źródło: „${entry.canonical_name}”.`, "Zatwierdzanie źródła")}>
                      ✓ Zatwierdź
                    </button>
                  )}
                  <button type="button" disabled={busy} onClick={() => setEditing(entry.id)}>✎ Edytuj</button>
                  <button type="button" disabled={busy}
                    title="To nie jest źródło tego dokumentu; kolejne wykrywanie nie zaproponuje go ponownie"
                    onClick={() => void update(entry, { review_status: "rejected" },
                      `Odrzucono źródło: „${entry.canonical_name}”.`, "Odrzucanie źródła")}>
                    🚫 Odrzuć
                  </button>
                </div>
              )}
              {editing === entry.id && (
                <EditForm entry={entry} busy={busy} onCancel={() => setEditing(null)}
                  onSave={(body) => void update(entry, body, `Zapisano źródło: „${body.name}”.`, "Zapis źródła")} />
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default ChapterSourcesPanel;
