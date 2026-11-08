import React from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

// The registry of concepts and ideologies ("Ciemne oświecenie"): a canonical entry with a description and names,
// plus the documents whose marked mentions (conceptName, /ner/:id) are linked to it. Tab "Nazwy do powiązania"
// lists marked names that are not linked to any concept yet. A name alone never links anything.

interface ConceptDocument { id: number; title: string | null; surfaces: string[] }
interface ConceptAlias { id: number; alias: string }
interface Concept {
  id: number; name: string; description: string | null; aliases: ConceptAlias[];
  document_count?: number; documents?: ConceptDocument[];
}
interface Suggestion { reason: string; score: number; concept: { id: number; name: string; description: string | null } }
interface UnlinkedGroup {
  name: string; name_key: string; mentions: number; document_count: number;
  documents: { id: number; title: string | null; mentions: number }[]; suggestions: Suggestion[];
}

const DEFAULT_PAGE_SIZE = 50;
const message = (reason: any) => reason?.response?.data?.message || reason?.message || "nieznany błąd";
const box: React.CSSProperties = { padding: "8px 10px", marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" };

const ConceptCard = ({ concept, apiUrl, headers, onChanged }: {
  concept: Concept; apiUrl: string; headers: Record<string, string>; onChanged: () => void;
}) => {
  const [editing, setEditing] = React.useState(false);
  const [name, setName] = React.useState(concept.name);
  const [description, setDescription] = React.useState(concept.description ?? "");
  const [newAlias, setNewAlias] = React.useState("");
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try { await action(); onChanged(); } catch (reason: any) { setError(message(reason)); } finally { setBusy(false); }
  };
  const save = () => run(async () => {
    await axios.patch(`${apiUrl}/concepts/${concept.id}`, {
      name: name.trim(), description: description.trim() || null, ...(newAlias.trim() && { aliases: [newAlias.trim()] }),
    }, { headers });
    setEditing(false);
    setNewAlias("");
  });

  return (
    <li style={box}>
      <strong>💡 {concept.name}</strong>{" "}
      <span style={{ color: "#64748b", fontSize: "0.85em" }}>#{concept.id} · {concept.document_count ?? 0} dok.</span>
      {!editing && (
        <div style={{ margin: "4px 0", color: concept.description ? undefined : "#94a3b8", whiteSpace: "pre-wrap" }}>
          {concept.description || "Brak opisu — dodaj go przyciskiem „Edytuj”."}
        </div>
      )}
      {editing && (
        <div style={{ margin: "6px 0" }}>
          <label style={{ display: "block" }}>Nazwa
            <input type="text" value={name} onChange={(event) => setName(event.target.value)}
              style={{ width: "100%", padding: "4px 6px", boxSizing: "border-box" }} />
          </label>
          <label style={{ display: "block", marginTop: 6 }}>Opis
            <textarea value={description} rows={5} onChange={(event) => setDescription(event.target.value)}
              style={{ width: "100%", padding: "4px 6px", boxSizing: "border-box" }} />
          </label>
          <label style={{ display: "block", marginTop: 6 }}>Dodaj nazwę (alias, np. wersja angielska)
            <input type="text" value={newAlias} onChange={(event) => setNewAlias(event.target.value)}
              style={{ width: "100%", padding: "4px 6px", boxSizing: "border-box" }} />
          </label>
        </div>
      )}
      <div style={{ color: "#475569", fontSize: "0.9em", margin: "2px 0" }}>
        Nazwy:{" "}
        {concept.aliases.map((alias) => (
          <span key={alias.id} style={{ marginRight: 8 }}>
            {alias.alias}
            {editing && concept.aliases.length > 1 && (
              <button type="button" aria-label={`Usuń nazwę ${alias.alias}`} disabled={busy}
                onClick={() => void run(() => axios.delete(`${apiUrl}/concepts/${concept.id}/aliases/${alias.id}`, { headers }))}
                style={{ marginLeft: 2 }}>×</button>
            )}
          </span>
        ))}
      </div>
      {(concept.documents?.length ?? 0) > 0 && (
        <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
          {concept.documents!.map((document) => (
            <li key={document.id}>
              <Link to={`/read/${document.id}`}>{document.title || `Dokument #${document.id}`}</Link>{" "}
              <Link to={`/ner/${document.id}`} style={{ fontSize: "0.85em" }}>NER</Link>{" "}
              <span style={{ color: "#64748b", fontSize: "0.85em" }}>({document.surfaces.join(", ")})</span>
            </li>
          ))}
        </ul>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
        {editing ? (
          <>
            <button type="button" className="button" disabled={busy || !name.trim()} onClick={() => void save()}>Zapisz</button>
            <button type="button" className="button" disabled={busy} onClick={() => {
              setEditing(false); setName(concept.name); setDescription(concept.description ?? ""); setNewAlias("");
            }}>Anuluj</button>
          </>
        ) : (
          <button type="button" className="button" onClick={() => setEditing(true)}>Edytuj</button>
        )}
        {confirmDelete ? (
          <>
            <span style={{ color: "#a33" }}>Usunąć pojęcie? Zaznaczenia w dokumentach zostają.</span>
            <button type="button" className="button" disabled={busy}
              onClick={() => void run(() => axios.delete(`${apiUrl}/concepts/${concept.id}`, { headers }))}>Tak, usuń</button>
            <button type="button" className="button" onClick={() => setConfirmDelete(false)}>Nie</button>
          </>
        ) : (
          <button type="button" className="button" onClick={() => setConfirmDelete(true)}>Usuń</button>
        )}
      </div>
      {error && <p role="alert" style={{ color: "#a33", margin: "4px 0 0" }}>{error}</p>}
    </li>
  );
};

const UnlinkedRow = ({ group, apiUrl, headers, onChanged }: {
  group: UnlinkedGroup; apiUrl: string; headers: Record<string, string>; onChanged: () => void;
}) => {
  const [description, setDescription] = React.useState("");
  const [conceptId, setConceptId] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try { await action(); onChanged(); } catch (reason: any) { setError(message(reason)); } finally { setBusy(false); }
  };
  const link = (id: number) => run(() => axios.post(`${apiUrl}/concepts/mentions/link`, { name: group.name, concept_id: id }, { headers }));

  return (
    <li style={box}>
      <strong>💡 {group.name}</strong>{" "}
      <span style={{ color: "#64748b", fontSize: "0.85em" }}>{group.document_count} dok. · {group.mentions} wzmianek</span>
      <div style={{ fontSize: "0.9em", color: "#475569" }}>
        {group.documents.slice(0, 5).map((document, index) => (
          <span key={document.id}>{index > 0 && ", "}<Link to={`/ner/${document.id}`}>{document.title || `#${document.id}`}</Link></span>
        ))}
        {group.documents.length > 5 && ` … (+${group.documents.length - 5})`}
      </div>
      {group.suggestions.map((suggestion) => (
        <div key={suggestion.concept.id} style={{ margin: "4px 0" }}>
          Czy to „{suggestion.concept.name}” (#{suggestion.concept.id}
          {suggestion.reason === "alias" ? ", ta sama nazwa" : `, podobna nazwa ${suggestion.score}`})?{" "}
          <button type="button" className="button" disabled={busy} onClick={() => void link(suggestion.concept.id)}>Tak, powiąż</button>{" "}
          <button type="button" className="button" disabled={busy} onClick={() => void run(() => axios.post(
            `${apiUrl}/concepts/mentions/reject`, { name: group.name, concept_id: suggestion.concept.id }, { headers }))}>To nie to</button>
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-start", marginTop: 6 }}>
        <textarea aria-label={`Opis pojęcia ${group.name}`} placeholder="Opis nowego pojęcia (opcjonalnie)" rows={2}
          value={description} onChange={(event) => setDescription(event.target.value)} style={{ minWidth: 260 }} />
        <button type="button" className="button" disabled={busy} onClick={() => void run(() => axios.post(
          `${apiUrl}/concepts/from_mention`, { name: group.name, ...(description.trim() && { description: description.trim() }) },
          { headers }))}>Utwórz pojęcie</button>
        <input type="number" aria-label={`Numer pojęcia dla ${group.name}`} placeholder="Powiąż z #" value={conceptId}
          onChange={(event) => setConceptId(event.target.value)} style={{ width: 110 }} />
        <button type="button" className="button" disabled={busy || !Number.isInteger(Number(conceptId)) || Number(conceptId) <= 0}
          onClick={() => void link(Number(conceptId))}>Powiąż z istniejącym</button>
      </div>
      {error && <p role="alert" style={{ color: "#a33", margin: "4px 0 0" }}>{error}</p>}
    </li>
  );
};

const Concepts = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "unlinked" ? "unlinked" : "registry";
  const q = searchParams.get("q") ?? "";
  const oneId = Number(searchParams.get("id") ?? "");
  const singleId = Number.isInteger(oneId) && oneId > 0 ? oneId : null;
  const requestedPageSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const pageSize = PAGE_SIZES.includes(requestedPageSize) ? requestedPageSize : DEFAULT_PAGE_SIZE;
  const requestedPage = Number(searchParams.get("page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const [queryText, setQueryText] = React.useState(q);
  const [concepts, setConcepts] = React.useState<Concept[]>([]);
  const [groups, setGroups] = React.useState<UnlinkedGroup[]>([]);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [version, setVersion] = React.useState(0);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    setSearchParams(next, { replace: true });
  };
  const reload = () => setVersion((current) => current + 1);

  React.useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError("");
    const request = singleId !== null && tab === "registry"
      ? axios.get(`${apiUrl}/concepts/${singleId}`, { headers }).then((response) => {
        setConcepts(response.data.concept ? [response.data.concept] : []);
        setTotal(response.data.concept ? 1 : 0);
      })
      : tab === "unlinked"
        ? axios.get(`${apiUrl}/concepts/unlinked`, { headers, params: { q, limit: pageSize, offset: (page - 1) * pageSize } })
          .then((response) => { setGroups(response.data.mentions ?? []); setTotal(response.data.total ?? 0); })
        : axios.get(`${apiUrl}/concepts`, { headers, params: { q, limit: pageSize, offset: (page - 1) * pageSize } })
          .then((response) => { setConcepts(response.data.concepts ?? []); setTotal(response.data.total ?? 0); });
    request
      .catch((reason: any) => { if (!cancelled) setError(`Nie udało się pobrać pojęć: ${message(reason)}`); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [apiUrl, headers, tab, q, page, pageSize, singleId, version]);

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Pojęcia i ideologie</h2>
      <p style={{ color: "#667", marginBottom: 10 }}>
        Pojęcia, nurty i terminy (np. „Ciemne oświecenie”), które chcesz zapamiętać. Zaznacz je w tekście na stronie NER
        (prawy klawisz → „💡 Pojęcie / ideologia”), a tu nadaj im opis i powiąż z dokumentami.
      </p>
      <div role="tablist" style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button type="button" role="tab" aria-selected={tab === "registry"} className="button"
          onClick={() => update({ tab: null, page: null, id: null })}>Rejestr</button>
        <button type="button" role="tab" aria-selected={tab === "unlinked"} className="button"
          onClick={() => update({ tab: "unlinked", page: null, id: null })}>Nazwy do powiązania</button>
      </div>
      {singleId !== null && tab === "registry" ? (
        <p><button type="button" className="button" onClick={() => update({ id: null })}>← Wszystkie pojęcia</button></p>
      ) : (
        <form onSubmit={(event) => { event.preventDefault(); update({ q: queryText.trim() || null, page: null }); }}
          style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 8 }}>
          <input type="search" aria-label="Szukaj pojęcia" placeholder="Szukaj w nazwach i opisie…" value={queryText}
            onChange={(event) => setQueryText(event.target.value)} style={{ padding: "4px 8px" }} />
          <button type="submit" className="button">Szukaj</button>
          <span style={{ color: "#64748b" }}>{isLoading ? "Wczytuję…" : `${total} ${tab === "unlinked" ? "nazw" : "pojęć"}`}</span>
        </form>
      )}
      {error && <p role="alert" style={{ color: "#a33" }}>{error}</p>}
      {!isLoading && !error && total === 0 && (
        <p style={{ color: "#667" }}>{tab === "unlinked" ? "Brak nazw do powiązania." : "Brak pojęć."}</p>
      )}
      {tab === "registry" ? (
        <ul aria-label="Pojęcia" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {concepts.map((concept) => (
            <ConceptCard key={concept.id} concept={concept} apiUrl={apiUrl} headers={headers} onChanged={reload} />
          ))}
        </ul>
      ) : (
        <ul aria-label="Nazwy do powiązania" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {groups.map((group) => (
            <UnlinkedRow key={group.name_key} group={group} apiUrl={apiUrl} headers={headers} onChanged={reload} />
          ))}
        </ul>
      )}
      {!(singleId !== null && tab === "registry") && (
        <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading}
          label={tab === "unlinked" ? "nazw" : "pojęć"}
          onPageChange={(next) => update({ page: next > 1 ? String(next) : null })} />
      )}
    </div>
  );
};

export default Concepts;
