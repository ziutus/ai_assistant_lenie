import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { PersonItem, PersonHeader } from "./persons";

// Review queue for manual_review person links (NER stage 4):
// GET /persons_review lists entries, PATCH /persons_review/<link_id> decides
// (approve / reject / merge with a person picked via GET /persons?q=).

interface ReviewEntry {
  link_id: number;
  document_id: number;
  document_title: string | null;
  document_type: string | null;
  person_id: number;
  canonical_name: string;
  description: string | null;
  wikidata_qid: string | null;
  aliases: string[];
  raw_mention: string;
  created_at: string | null;
}

const EDITOR_TYPES = ["webpage", "link", "youtube", "movie", "email"];

const MergePicker = ({
  entry,
  onMerge,
  onCancel,
}: {
  entry: ReviewEntry;
  onMerge: (targetPersonId: number) => void;
  onCancel: () => void;
}) => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<PersonItem[]>([]);
  const [isSearching, setIsSearching] = React.useState(false);
  const [message, setMessage] = React.useState("");

  const search = async () => {
    setIsSearching(true);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/persons`, {
        params: query.trim() ? { q: query.trim() } : {},
        headers: { "x-api-key": `${apiKey}` },
      });
      const found = (response.data.persons ?? []).filter((p: PersonItem) => p.id !== entry.person_id);
      setResults(found);
      if (!found.length) {
        setMessage("Brak innych osób pasujących do zapytania.");
      }
    } catch (error: any) {
      console.error("Error searching persons for merge", error);
      setMessage(`Nie udało się wyszukać osób: ${error.response?.data?.message || error.message}`);
    }
    setIsSearching(false);
  };

  return (
    <div style={{ marginTop: 8, padding: 8, background: "#f5f7fa", border: "1px solid #d5dde8", borderRadius: 6 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <input
          type="text"
          value={query}
          placeholder="Szukaj osoby docelowej..."
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              search();
            }
          }}
          style={{ minWidth: 260, padding: "4px 8px" }}
          disabled={isSearching}
        />
        <button className={"button"} type="button" disabled={isSearching} onClick={search}>
          Szukaj
        </button>
        <button className={"button"} type="button" onClick={onCancel}>
          Anuluj
        </button>
      </div>
      {message && <div style={{ marginTop: 6, color: "#a33" }}>{message}</div>}
      <ul style={{ listStyle: "none", padding: 0, margin: "6px 0 0" }}>
        {results.map((p) => (
          <li key={p.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0" }}>
            <button className={"button"} type="button" onClick={() => onMerge(p.id)}>
              Scal z tą osobą
            </button>
            <PersonHeader person={p} />
          </li>
        ))}
      </ul>
    </div>
  );
};

const PersonsReview = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [entries, setEntries] = React.useState<ReviewEntry[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [busyLinkId, setBusyLinkId] = React.useState<number | null>(null);
  const [mergeLinkId, setMergeLinkId] = React.useState<number | null>(null);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);

  const headers = {
    "Content-Type": "application/json",
    "x-api-key": `${apiKey}`,
  };

  const fetchQueue = async () => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/persons_review`, { headers });
      setEntries(response.data.entries ?? []);
    } catch (error: any) {
      console.error("Error fetching review queue", error);
      setIsError(true);
      setMessage(`Nie udało się pobrać kolejki: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchQueue();
  }, []);

  const decide = async (entry: ReviewEntry, action: "approve" | "reject" | "merge", targetPersonId?: number) => {
    setBusyLinkId(entry.link_id);
    setIsError(false);
    setMessage("");
    try {
      const body: Record<string, unknown> = { action };
      if (targetPersonId != null) {
        body.target_person_id = targetPersonId;
      }
      const response = await axios.patch(`${apiUrl}/persons_review/${entry.link_id}`, body, { headers });
      setEntries((prev) => prev.filter((e) => e.link_id !== entry.link_id));
      setMergeLinkId(null);
      const labels: Record<string, string> = {
        approve: "zatwierdzono",
        reject: "odrzucono",
        merge: "scalono",
      };
      let info = `„${entry.raw_mention}” — ${labels[action]}.`;
      if (response.data.person_deleted) {
        info += " Osieroconą osobę usunięto z rejestru.";
      }
      setMessage(info);
    } catch (error: any) {
      console.error("Error deciding review entry", error);
      setIsError(true);
      setMessage(`Nie udało się zapisać decyzji: ${error.response?.data?.message || error.message}`);
    }
    setBusyLinkId(null);
  };

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Osoby — kolejka weryfikacji</h2>
      <p style={{ color: "#667", marginBottom: 12 }}>
        Wzmianki o osobach, których automat nie rozstrzygnął (confidence = manual_review). Zatwierdź, odrzuć
        albo scal z istniejącą osobą z rejestru.
      </p>

      <button className={"button"} type="button" disabled={isLoading} onClick={fetchQueue}>
        Odśwież
      </button>

      {isLoading && <div className={"loader"}></div>}
      {message && (
        <p className={isError ? "errorText" : undefined} style={isError ? undefined : { color: "#2e7d43" }}>
          {message}
        </p>
      )}

      {!isLoading && !entries.length && (
        <p style={{ marginTop: 14, color: "#667" }}>Kolejka jest pusta — brak wpisów do weryfikacji. 🎉</p>
      )}

      <ul style={{ listStyle: "none", padding: 0, marginTop: 14 }}>
        {entries.map((entry) => (
          <li
            key={entry.link_id}
            style={{ padding: "10px 8px", borderBottom: "1px solid #eee", opacity: busyLinkId === entry.link_id ? 0.5 : 1 }}
          >
            <div>
              wzmianka: <strong>„{entry.raw_mention}”</strong>
              <span style={{ margin: "0 6px", color: "#667" }}>→</span>
              <PersonHeader person={entry} />
            </div>
            <div style={{ fontSize: "0.9em", color: "#667", margin: "4px 0" }}>
              Dokument:{" "}
              {entry.document_type && EDITOR_TYPES.includes(entry.document_type) ? (
                <NavLink to={`/${entry.document_type}/${entry.document_id}`}>
                  {entry.document_title || `Dokument ${entry.document_id}`}
                </NavLink>
              ) : (
                <span>{entry.document_title || `Dokument ${entry.document_id}`}</span>
              )}
              <NavLink to={`/read/${entry.document_id}`} style={{ marginLeft: 8, color: "#0369a1" }}>
                📖 Czytaj
              </NavLink>
              {entry.created_at && <span style={{ marginLeft: 8 }}>({entry.created_at.slice(0, 10)})</span>}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className={"button"}
                type="button"
                disabled={busyLinkId === entry.link_id}
                onClick={() => decide(entry, "approve")}
              >
                ✓ Zatwierdź
              </button>
              <button
                className={"button"}
                type="button"
                disabled={busyLinkId === entry.link_id}
                onClick={() => decide(entry, "reject")}
              >
                ✗ Odrzuć
              </button>
              <button
                className={"button"}
                type="button"
                disabled={busyLinkId === entry.link_id}
                onClick={() => setMergeLinkId(mergeLinkId === entry.link_id ? null : entry.link_id)}
              >
                ⇄ Scal z inną osobą...
              </button>
            </div>
            {mergeLinkId === entry.link_id && (
              <MergePicker
                entry={entry}
                onMerge={(targetPersonId) => decide(entry, "merge", targetPersonId)}
                onCancel={() => setMergeLinkId(null)}
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default PersonsReview;
