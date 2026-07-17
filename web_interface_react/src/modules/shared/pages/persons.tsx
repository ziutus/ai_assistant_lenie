import React from "react";
import axios from "axios";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// Person registry browser (NER stage 4): fuzzy search over persons/aliases
// (GET /persons?q=) and the person -> documents view (GET /person_documents).

export interface PersonItem {
  id: number;
  uuid: string;
  canonical_name: string;
  wikidata_qid: string | null;
  description: string | null;
  aliases: string[];
}

interface PersonDocument {
  id: number;
  title: string;
  document_type: string;
  raw_mention: string;
  confidence: string;
  mention_count: number;
  role: string;
}

// Per-chapter occurrence counts (GET /document/:id/entity_occurrences?text=)
// — the "occurrences in this book" drill-down for long documents.
interface ChapterOccurrence {
  position: number;
  title: string;
  count: number;
}

const EDITOR_TYPES = ["webpage", "link", "youtube", "movie", "email"];

const CONFIDENCE_LABELS: Record<string, string> = {
  wikidata_matched: "✓ Wikidata",
  alias_matched: "✓ alias",
  manual_confirmed: "✓ potwierdzone",
  manual_review: "? do weryfikacji",
};

export const PersonHeader = ({ person }: { person: Pick<PersonItem, "canonical_name" | "description" | "wikidata_qid"> & { aliases?: string[] } }) => (
  <div style={{ display: "inline-block", verticalAlign: "top" }}>
    <strong>{person.canonical_name}</strong>
    {person.wikidata_qid && (
      <a
        href={`https://www.wikidata.org/wiki/${person.wikidata_qid}`}
        target="_blank"
        rel="noreferrer"
        style={{ marginLeft: 8, fontSize: "0.85em", color: "#0369a1" }}
      >
        {person.wikidata_qid}
      </a>
    )}
    {person.description && <span style={{ marginLeft: 8, color: "#667" }}>{person.description}</span>}
    {!!person.aliases?.length && (
      <div style={{ fontSize: "0.85em", color: "#667" }}>Aliasy: {person.aliases.join(", ")}</div>
    )}
  </div>
);

const Persons = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  // ?q= pre-fills the search — unresolved person chips in the reader link here
  const initialQuery = searchParams.get("q") ?? "";
  const [query, setQuery] = React.useState(initialQuery);
  const [persons, setPersons] = React.useState<PersonItem[]>([]);
  const [person, setPerson] = React.useState<
    { canonical_name: string; description: string | null; wikidata_qid: string | null } | null
  >(null);
  const [documents, setDocuments] = React.useState<PersonDocument[]>([]);
  // per-document chapter drill-down ("wystąpienia w tej książce")
  const [occurrences, setOccurrences] = React.useState<Record<number, ChapterOccurrence[] | "loading">>({});
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const authoredDocuments = documents.filter((doc) => doc.role === "author");
  const mentionedDocuments = documents.filter((doc) => doc.role !== "author");

  const headers = {
    "Content-Type": "application/x-www-form-urlencoded",
    "x-api-key": `${apiKey}`,
  };

  const search = async (q: string) => {
    setIsLoading(true);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/persons`, { params: q ? { q } : {}, headers });
      setPersons(response.data.persons ?? []);
      if (!(response.data.persons ?? []).length) {
        setMessage(q ? "Brak osób pasujących do zapytania." : "Rejestr osób jest pusty.");
      }
    } catch (error: any) {
      console.error("Error searching persons", error);
      setMessage(`Nie udało się wyszukać osób: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    search(initialQuery);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleOccurrences = async (doc: PersonDocument) => {
    if (occurrences[doc.id]) {
      setOccurrences((prev) => {
        const next = { ...prev };
        delete next[doc.id];
        return next;
      });
      return;
    }
    setOccurrences((prev) => ({ ...prev, [doc.id]: "loading" }));
    try {
      const response = await axios.get(`${apiUrl}/document/${doc.id}/entity_occurrences`, {
        params: { text: doc.raw_mention }, headers,
      });
      setOccurrences((prev) => ({ ...prev, [doc.id]: response.data.occurrences ?? [] }));
    } catch (error: any) {
      console.error("Error fetching occurrences", error);
      setOccurrences((prev) => {
        const next = { ...prev };
        delete next[doc.id];
        return next;
      });
      setMessage(`Nie udało się pobrać wystąpień: ${error.response?.data?.message || error.message}`);
    }
  };

  React.useEffect(() => {
    setPerson(null);
    setDocuments([]);
    setOccurrences({});
    if (!id) {
      return;
    }
    setIsLoading(true);
    axios
      .get(`${apiUrl}/person_documents`, { params: { id }, headers })
      .then((response) => {
        setPerson(response.data.person);
        setDocuments(response.data.documents ?? []);
      })
      .catch((error) => {
        console.error("Error fetching person documents", error);
        setMessage(`Nie udało się pobrać artykułów osoby: ${error.response?.data?.message || error.message}`);
      })
      .finally(() => setIsLoading(false));
  }, [id]);

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Osoby</h2>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          search(query.trim());
        }}
        style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14 }}
      >
        <input
          type="text"
          value={query}
          placeholder="Szukaj osoby (nazwa lub alias)..."
          onChange={(e) => setQuery(e.target.value)}
          style={{ minWidth: 320, padding: "6px 10px" }}
          disabled={isLoading}
        />
        <button type="submit" className={"button"} disabled={isLoading}>
          Szukaj
        </button>
      </form>

      {isLoading && <div className={"loader"}></div>}
      {message && <p className={"errorText"}>{message}</p>}

      {id && person ? (
        <div style={{ marginBottom: 20, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
          <PersonHeader person={person} />
          <h3 style={{ margin: "12px 0 6px" }}>Artykuły autora ({authoredDocuments.length})</h3>
          {!authoredDocuments.length && <div style={{ color: "#667" }}>Brak dokumentów oznaczonych jako autorstwa tej osoby.</div>}
          <ul style={{ listStyle: "none", padding: 0 }}>
            {authoredDocuments.map((doc) => (
              <li key={doc.id} style={{ padding: "6px 0", borderBottom: "1px solid #eee" }}>
                <span style={{ color: "#667", fontSize: "0.85em", marginRight: 8 }}>[{doc.document_type}]</span>
                <NavLink to={`/read/${doc.id}?highlight=${encodeURIComponent(doc.raw_mention)}`}>
                  {doc.title || `Dokument ${doc.id}`}
                </NavLink>
                {doc.mention_count > 0 && <strong style={{ marginLeft: 8, color: "#334155" }}>×{doc.mention_count}</strong>}
                {EDITOR_TYPES.includes(doc.document_type) && (
                  <NavLink to={`/${doc.document_type}/${doc.id}`} style={{ marginLeft: 10, fontSize: "0.85em", color: "#0369a1" }}>
                    ✏️ Edytuj
                  </NavLink>
                )}
                <button
                  type="button"
                  onClick={() => toggleOccurrences(doc)}
                  style={{ marginLeft: 10, fontSize: "0.85em", color: "#0369a1", border: "none", background: "none", cursor: "pointer", padding: 0 }}
                >
                  {occurrences[doc.id] ? "▾ rozdziały" : "▸ rozdziały"}
                </button>
                <span style={{ marginLeft: 10, fontSize: "0.85em", color: "#667" }}>
                  wzmianka: „{doc.raw_mention}” · {CONFIDENCE_LABELS[doc.confidence] ?? doc.confidence}
                </span>
                {occurrences[doc.id] === "loading" && (
                  <div style={{ fontSize: "0.85em", color: "#94a3b8", margin: "4px 0 0 20px" }}>Ładowanie…</div>
                )}
                {Array.isArray(occurrences[doc.id]) && (
                  <div style={{ fontSize: "0.85em", margin: "4px 0 0 20px" }}>
                    {(occurrences[doc.id] as ChapterOccurrence[]).length === 0 && (
                      <span style={{ color: "#94a3b8" }}>Brak rozdziałów (dokument bez struktury) lub wystąpień.</span>
                    )}
                    {(occurrences[doc.id] as ChapterOccurrence[]).map((o) => (
                      <div key={o.position} style={{ padding: "1px 0" }}>
                        <NavLink
                          to={`/read/${doc.id}?chapter=${o.position}&highlight=${encodeURIComponent(doc.raw_mention)}`}
                          style={{ color: "#0369a1" }}
                        >
                          {o.position}. {o.title}
                        </NavLink>
                        <span style={{ color: "#667" }}> ×{o.count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
          {mentionedDocuments.length > 0 && <>
            <h3 style={{ margin: "18px 0 6px" }}>Dokumenty, w których jest wspomniany ({mentionedDocuments.length})</h3>
            <ul style={{ listStyle: "none", padding: 0 }}>
              {mentionedDocuments.map((doc) => (
                <li key={doc.id} style={{ padding: "6px 0", borderBottom: "1px solid #eee" }}>
                  <span style={{ color: "#667", fontSize: "0.85em", marginRight: 8 }}>[{doc.document_type}]</span>
                  <NavLink to={`/read/${doc.id}?highlight=${encodeURIComponent(doc.raw_mention)}`}>
                    {doc.title || `Dokument ${doc.id}`}
                  </NavLink>
                  {doc.mention_count > 0 && <strong style={{ marginLeft: 8, color: "#334155" }}>×{doc.mention_count}</strong>}
                </li>
              ))}
            </ul>
          </>}
          <button className={"button"} type="button" onClick={() => navigate("/persons")}>
            ← Wróć do listy
          </button>
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {persons.map((p) => (
            <li
              key={p.id}
              style={{ padding: "8px 6px", borderBottom: "1px solid #eee", cursor: "pointer" }}
              onClick={() => navigate(`/persons/${p.id}`)}
            >
              <PersonHeader person={p} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default Persons;
