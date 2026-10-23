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

export interface PersonSource {
  id: number;
  name: string;
  kind: string | null;
  role: string;
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
  // Public figures the user follows (course authors, channel hosts): kind === "public".
  kind?: string | null;
  role?: string | null;
  obsidian_note_path?: string | null;
  sources?: PersonSource[];
}

export const sourceRoleLabels: Record<string, string> = {
  author: "autor", host: "prowadzący", instructor: "wykładowca", guest: "gość", other: "inne",
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

export const PersonHeader = ({ person }: { person: Pick<PersonItem, "canonical_name" | "description" | "wikidata_qid"> & { aliases?: string[]; kind?: string | null; role?: string | null; sources?: PersonSource[] } }) => (
  <div style={{ display: "inline-block", verticalAlign: "top" }}>
    <strong>{person.canonical_name}</strong>
    {person.kind === "public" && (
      <span title="Osoba publiczna, którą obserwuję" style={{ marginLeft: 8, background: "#ecfeff", color: "#155e75", borderRadius: 4, padding: "1px 6px", fontSize: "0.8em" }}>
        publiczna{person.role ? ` · ${person.role}` : ""}
      </span>
    )}
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
    {!!person.sources?.length && (
      <div style={{ fontSize: "0.85em", color: "#667" }}>
        Źródła: {person.sources.map((source) => `${source.name} (${sourceRoleLabels[source.role] ?? source.role})`).join(", ")}
      </div>
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
  const [publicOnly, setPublicOnly] = React.useState(searchParams.get("kind") === "public");
  const [person, setPerson] = React.useState<
    {
      canonical_name: string; description: string | null; long_description?: string | null; wikidata_qid: string | null;
      links?: PersonLink[]; aliases?: string[]; kind?: string | null; role?: string | null;
      obsidian_note_path?: string | null; sources?: PersonSource[];
    } | null
  >(null);
  // Edit form of the registry person: name (the old one stays an alias), description, Wikidata id, aliases,
  // and whether this is a public figure the user follows (with what they are known for).
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState({
    name: "", description: "", long_description: "", qid: "", aliases: "", links: [] as PersonLink[],
    isPublic: false, role: "", note: "",
  });
  // "Add a public person" form on the list page.
  const [addForm, setAddForm] = React.useState({ name: "", role: "", url: "" });
  const [adding, setAdding] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
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

  const search = async (q: string, nextPage = 1, onlyPublic = publicOnly) => {
    setIsLoading(true);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/persons`, {
        params: { ...(q ? { q } : {}), ...(onlyPublic ? { kind: "public" } : {}), limit: pageSize, offset: (nextPage - 1) * pageSize },
        headers,
      });
      setPersons(response.data.persons ?? []);
      setTotal(response.data.total ?? response.data.persons?.length ?? 0);
      setPage(nextPage);
      setSearchParams({
        ...(q ? { q } : {}), ...(onlyPublic ? { kind: "public" } : {}), ...(nextPage > 1 ? { page: String(nextPage) } : {}),
      }, { replace: true });
      if (!(response.data.persons ?? []).length) {
        setMessage(q ? "Brak osób pasujących do zapytania." : onlyPublic ? "Nie ma jeszcze osób publicznych." : "Rejestr osób jest pusty.");
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

  const startEdit = () => {
    if (!person) return;
    setDraft({
      name: person.canonical_name, description: person.description ?? "", qid: person.wikidata_qid ?? "",
      aliases: (person.aliases ?? []).join("\n"),
      long_description: person.long_description ?? "", links: (person.links ?? []).map((link) => ({ ...link })),
      isPublic: person.kind === "public", role: person.role ?? "", note: person.obsidian_note_path ?? "",
    });
    setEditing(true);
  };

  const addPublicPerson = async () => {
    if (!addForm.name.trim()) return;
    setAdding(true);
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/persons`, {
        canonical_name: addForm.name.trim(), kind: "public", role: addForm.role.trim(),
        links: addForm.url.trim() ? [{ url: addForm.url.trim(), label: "" }] : [],
      }, { headers: { ...headers, "Content-Type": "application/json" } });
      setAddForm({ name: "", role: "", url: "" });
      navigate(`/persons/${response.data.person.id}`);
    } catch (error: any) {
      const existing = error.response?.data?.existing_person_id;
      setMessage(existing
        ? `${error.response.data.message} Otwórz ją i zaznacz „osoba publiczna”: /persons/${existing}`
        : `Nie udało się dodać osoby: ${error.response?.data?.message || error.message}`);
    }
    setAdding(false);
  };

  const saveEdit = async () => {
    if (!id || !draft.name.trim()) return;
    setSaving(true);
    setMessage("");
    try {
      const response = await axios.patch(`${apiUrl}/persons/${id}`, {
        canonical_name: draft.name.trim(), description: draft.description, wikidata_qid: draft.qid.trim(),
        long_description: draft.long_description,
        kind: draft.isPublic ? "public" : "", role: draft.role.trim(), obsidian_note_path: draft.note.trim(),
        links: draft.links.filter((link) => link.url.trim()).map((link) => ({ url: link.url.trim(), label: link.label.trim() })),
        aliases: draft.aliases.split("\n").map((alias) => alias.trim()).filter(Boolean),
      }, { headers: { ...headers, "Content-Type": "application/json" } });
      setPerson(response.data.person);
      setEditing(false);
    } catch (error: any) {
      setMessage(`Nie udało się zapisać osoby: ${error.response?.data?.message || error.message}`);
    }
    setSaving(false);
  };

  React.useEffect(() => {
    setEditing(false);
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
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
          title="Osoby publiczne, które obserwuję: autorzy kursów, prowadzący kanały, pisarze.">
          <input type="checkbox" checked={publicOnly} disabled={isLoading}
            onChange={(e) => { setPublicOnly(e.target.checked); void search(query.trim(), 1, e.target.checked); }} />
          Tylko osoby publiczne
        </label>
      </form>

      {!id && (
        <details style={{ marginBottom: 14 }}>
          <summary style={{ cursor: "pointer", color: "#0369a1" }}>+ Dodaj osobę publiczną</summary>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            <input type="text" placeholder="Imię i nazwisko" value={addForm.name} disabled={adding}
              onChange={(e) => setAddForm({ ...addForm, name: e.target.value })} style={{ minWidth: 220 }} />
            <input type="text" placeholder="Kim jest (np. prowadzący kanał, autor kursu)" value={addForm.role} disabled={adding}
              onChange={(e) => setAddForm({ ...addForm, role: e.target.value })} style={{ minWidth: 280 }} />
            <input type="url" placeholder="Link (kanał, strona, LinkedIn…)" value={addForm.url} disabled={adding}
              onChange={(e) => setAddForm({ ...addForm, url: e.target.value })} style={{ minWidth: 260 }} />
            <button type="button" className={"button"} disabled={adding || !addForm.name.trim()} onClick={() => void addPublicPerson()}>
              Dodaj
            </button>
          </div>
        </details>
      )}

      {isLoading && <div className={"loader"}></div>}
      {message && <p className={"errorText"}>{message}</p>}

      {!id && <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading} label="osób"
        onPageChange={nextPage => { void search(query.trim(), nextPage); }} />}

      {id && person ? (
        <div style={{ marginBottom: 20, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
          <PersonHeader person={person} />
          {!editing && (
            <div style={{ marginTop: 8 }}>
              {!!person.sources?.length && (
                <div style={{ margin: "6px 0" }}>
                  Źródła:{" "}
                  {person.sources.map((source, index) => (
                    <span key={source.id}>
                      {index > 0 && " · "}
                      <NavLink to="/sources" style={{ color: "#0369a1" }}>{source.name}</NavLink>
                      <span style={{ color: "#667" }}> ({sourceRoleLabels[source.role] ?? source.role})</span>
                    </span>
                  ))}
                </div>
              )}
              {person.obsidian_note_path && (
                <div style={{ margin: "6px 0", color: "#667", fontSize: "0.85em" }}>Notatka w Obsidianie: {person.obsidian_note_path}</div>
              )}
              {person.long_description && (
                <p style={{ whiteSpace: "pre-wrap", margin: "6px 0" }}>{person.long_description}</p>
              )}
              {!!person.links?.length && (
                <div style={{ margin: "6px 0" }}>
                  🔗{" "}
                  {person.links.map((link, index) => (
                    <span key={link.url}>
                      {index > 0 && " · "}
                      <a href={link.url} target="_blank" rel="noreferrer" style={{ color: "#0369a1" }}>{linkLabel(link)}</a>
                    </span>
                  ))}
                </div>
              )}
              <button type="button" className={"button"} onClick={startEdit}>✏️ Edytuj osobę</button>
            </div>
          )}
          {editing && (
            <div style={{ marginTop: 10, padding: 8, background: "#f0f6ff", borderRadius: 6, display: "grid", gap: 6, maxWidth: 520 }}>
              <label>Nazwisko (poprzednie zostanie aliasem)
                <input value={draft.name} maxLength={500} style={{ width: "100%" }}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </label>
              <label>Opis
                <input value={draft.description} style={{ width: "100%" }}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <input type="checkbox" checked={draft.isPublic}
                  onChange={(e) => setDraft({ ...draft, isPublic: e.target.checked })} />
                Osoba publiczna, którą obserwuję
              </label>
              {draft.isPublic && <>
                <label>Kim jest (np. prowadzący kanał, autor kursu)
                  <input value={draft.role} maxLength={100} style={{ width: "100%" }}
                    onChange={(e) => setDraft({ ...draft, role: e.target.value })} />
                </label>
                <label>Notatka w Obsidianie (ścieżka w vaulcie)
                  <input value={draft.note} style={{ width: "100%" }}
                    onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
                </label>
              </>}
              <label>Długi opis (tylko na tej stronie)
                <textarea rows={8} value={draft.long_description} style={{ width: "100%" }}
                  onChange={(e) => setDraft({ ...draft, long_description: e.target.value })} />
              </label>
              <div>
                Linki (np. Wikipedia)
                {draft.links.map((link, index) => (
                  <div key={index} style={{ display: "flex", gap: 6, marginTop: 4 }}>
                    <input type="url" value={link.url} placeholder="https://pl.wikipedia.org/wiki/…" style={{ flex: 3 }}
                      onChange={(e) => setDraft({ ...draft, links: draft.links.map((l, i) => (i === index ? { ...l, url: e.target.value } : l)) })} />
                    <input type="text" value={link.label} placeholder="Etykieta (np. Wikipedia)" style={{ flex: 1 }}
                      onChange={(e) => setDraft({ ...draft, links: draft.links.map((l, i) => (i === index ? { ...l, label: e.target.value } : l)) })} />
                    <button type="button" aria-label="Usuń link"
                      onClick={() => setDraft({ ...draft, links: draft.links.filter((_, i) => i !== index) })}>×</button>
                  </div>
                ))}
                <button type="button" style={{ marginTop: 6 }}
                  onClick={() => setDraft({ ...draft, links: [...draft.links, { url: "", label: "" }] })}>+ Dodaj link</button>
              </div>
              <label>Identyfikator Wikidata (np. Q12345, puste = brak)
                <input value={draft.qid} style={{ width: "100%" }}
                  onChange={(e) => setDraft({ ...draft, qid: e.target.value })} />
              </label>
              <label>Aliasy (jeden w wierszu)
                <textarea rows={4} value={draft.aliases} style={{ width: "100%" }}
                  onChange={(e) => setDraft({ ...draft, aliases: e.target.value })} />
              </label>
              <div>
                <button type="button" className={"button"} disabled={saving || !draft.name.trim()} onClick={() => void saveEdit()}>Zapisz</button>
                <button type="button" disabled={saving} onClick={() => setEditing(false)} style={{ marginLeft: 8 }}>Anuluj</button>
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
