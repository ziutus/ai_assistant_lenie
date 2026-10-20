import React from "react";
import axios from "axios";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination } from "../components/Pagination/pagination";

// Person registry browser (NER stage 4): fuzzy search over persons/aliases
// (GET /persons?q=) and the person -> documents view (GET /person_documents).

export interface PersonLink {
  url: string;
  label: string;
}

export interface PersonItem {
  id: number;
  uuid: string;
  canonical_name: string;
  wikidata_qid: string | null;
  description: string | null;
  long_description?: string | null;
  links?: PersonLink[];
  aliases: string[];
}

interface PersonDetail {
  canonical_name: string;
  description: string | null;
  long_description: string | null;
  wikidata_qid: string | null;
  links: PersonLink[];
  aliases?: string[];
}

export const linkLabel = (link: PersonLink): string => {
  if (link.label) {
    return link.label;
  }
  try {
    return new URL(link.url).hostname.replace(/^www\./, "");
  } catch {
    return link.url;
  }
};

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
  const [searchParams, setSearchParams] = useSearchParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  // ?q= pre-fills the search — unresolved person chips in the reader link here
  const initialQuery = searchParams.get("q") ?? "";
  const [query, setQuery] = React.useState(initialQuery);
  const [persons, setPersons] = React.useState<PersonItem[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(Number(searchParams.get("page")) || 1);
  const pageSize = 50;
  const [person, setPerson] = React.useState<PersonDetail | null>(null);
  const [isEditing, setIsEditing] = React.useState(false);
  const [draft, setDraft] = React.useState({ description: "", long_description: "", links: [] as PersonLink[] });
  const [isSaving, setIsSaving] = React.useState(false);
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

  const search = async (q: string, nextPage = 1) => {
    setIsLoading(true);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/persons`, { params: { ...(q ? { q } : {}), limit: pageSize, offset: (nextPage - 1) * pageSize }, headers });
      setPersons(response.data.persons ?? []);
      setTotal(response.data.total ?? response.data.persons?.length ?? 0);
      setPage(nextPage);
      setSearchParams({ ...(q ? { q } : {}), ...(nextPage > 1 ? { page: String(nextPage) } : {}) }, { replace: true });
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
    search(initialQuery, page);
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

  const startEditing = () => {
    if (!person) {
      return;
    }
    setDraft({
      description: person.description ?? "",
      long_description: person.long_description ?? "",
      links: (person.links ?? []).map((l) => ({ ...l })),
    });
    setIsEditing(true);
  };

  const saveProfile = async () => {
    setIsSaving(true);
    setMessage("");
    try {
      const response = await axios.patch(
        `${apiUrl}/persons/${id}`,
        {
          description: draft.description,
          long_description: draft.long_description,
          links: draft.links.filter((l) => l.url.trim()).map((l) => ({ url: l.url.trim(), label: l.label.trim() })),
        },
        { headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` } },
      );
      setPerson((prev) => (prev ? { ...prev, ...response.data.person } : prev));
      setIsEditing(false);
    } catch (error: any) {
      console.error("Error saving person", error);
      setMessage(`Nie udało się zapisać osoby: ${error.response?.data?.message || error.message}`);
    }
    setIsSaving(false);
  };

  React.useEffect(() => {
    setPerson(null);
    setIsEditing(false);
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

      {!id && <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading} label="osób"
        onPageChange={nextPage => { void search(query.trim(), nextPage); }} />}

      {id && person ? (
        <div style={{ marginBottom: 20, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
          <PersonHeader person={person} />
          {!isEditing && (
            <div style={{ marginTop: 8 }}>
              {person.long_description && (
                <p style={{ whiteSpace: "pre-wrap", margin: "6px 0" }}>{person.long_description}</p>
              )}
              {!!person.links?.length && (
                <div style={{ margin: "6px 0" }}>
                  🔗{" "}
                  {person.links.map((link, index) => (
                    <span key={link.url}>
                      {index > 0 && " · "}
                      <a href={link.url} target="_blank" rel="noreferrer" style={{ color: "#0369a1" }}>
                        {linkLabel(link)}
                      </a>
                    </span>
                  ))}
                </div>
              )}
              <button type="button" className={"button"} onClick={startEditing}>
                ✏️ Edytuj opisy i linki
              </button>
            </div>
          )}
          {isEditing && (
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8, maxWidth: 720 }}>
              <label>
                Krótki opis (podpowiedź przy najechaniu na osobę w czytniku)
                <input
                  type="text"
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  style={{ width: "100%", padding: "6px 10px" }}
                />
              </label>
              <label>
                Długi opis (tylko na tej stronie)
                <textarea
                  value={draft.long_description}
                  rows={8}
                  onChange={(e) => setDraft({ ...draft, long_description: e.target.value })}
                  style={{ width: "100%", padding: "6px 10px" }}
                />
              </label>
              <div>
                Linki (np. Wikipedia)
                {draft.links.map((link, index) => (
                  <div key={index} style={{ display: "flex", gap: 6, marginTop: 4 }}>
                    <input
                      type="url"
                      value={link.url}
                      placeholder="https://pl.wikipedia.org/wiki/…"
                      onChange={(e) => setDraft({ ...draft, links: draft.links.map((l, i) => (i === index ? { ...l, url: e.target.value } : l)) })}
                      style={{ flex: 3, padding: "6px 10px" }}
                    />
                    <input
                      type="text"
                      value={link.label}
                      placeholder="Etykieta (np. Wikipedia)"
                      onChange={(e) => setDraft({ ...draft, links: draft.links.map((l, i) => (i === index ? { ...l, label: e.target.value } : l)) })}
                      style={{ flex: 1, padding: "6px 10px" }}
                    />
                    <button
                      type="button"
                      aria-label="Usuń link"
                      onClick={() => setDraft({ ...draft, links: draft.links.filter((_, i) => i !== index) })}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <div style={{ marginTop: 6 }}>
                  <button
                    type="button"
                    onClick={() => setDraft({ ...draft, links: [...draft.links, { url: "", label: "" }] })}
                  >
                    + Dodaj link
                  </button>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className={"button"} disabled={isSaving} onClick={saveProfile}>
                  Zapisz
                </button>
                <button type="button" className={"button"} disabled={isSaving} onClick={() => setIsEditing(false)}>
                  Anuluj
                </button>
              </div>
            </div>
          )}
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
        <>
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
        {!id && <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading} label="osób"
          onPageChange={nextPage => { void search(query.trim(), nextPage); }} />}
        </>
      )}
    </div>
  );
};

export default Persons;
