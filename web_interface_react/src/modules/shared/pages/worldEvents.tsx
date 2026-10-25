import React from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

// Events of general knowledge ("Galanbard 2026", "szczyt NATO w Hadze") that a reviewer marked in document
// texts on /ner/:id (document_entities, entity_type eventName), grouped by name across documents. Not the
// private events of the contact book (/contact-events).

interface EventDocument { id: number; title: string | null; mentions: number; entity_id: number }
interface EventRow { name: string; description: string | null; mentions: number; document_count: number; documents: EventDocument[] }

const DEFAULT_PAGE_SIZE = 50;

const WorldEvents = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const requestedPageSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const pageSize = PAGE_SIZES.includes(requestedPageSize) ? requestedPageSize : DEFAULT_PAGE_SIZE;
  const requestedPage = Number(searchParams.get("page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const [queryText, setQueryText] = React.useState(q);
  const [rows, setRows] = React.useState<EventRow[]>([]);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    setSearchParams(next, { replace: true });
  };

  React.useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError("");
    axios.get(`${apiUrl}/entity_events`, { headers, params: { q, limit: pageSize, offset: (page - 1) * pageSize } })
      .then((response) => {
        if (cancelled) return;
        setRows(response.data.events ?? []);
        setTotal(response.data.total ?? 0);
      })
      .catch((reason: any) => {
        if (!cancelled) setError(`Nie udało się pobrać wydarzeń: ${reason.response?.data?.message || reason.message}`);
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [apiUrl, headers, q, page, pageSize]);

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Wydarzenia w tekstach</h2>
      <p style={{ color: "#667", marginBottom: 10 }}>
        Wydarzenia ogólne (ćwiczenia, szczyty, operacje), które oznaczyłeś w tekstach dokumentów prawym klawiszem na
        stronie NER. To nie są prywatne wydarzenia z książki kontaktów — te są w zakładce „Wydarzenia”.
      </p>
      <form onSubmit={(event) => { event.preventDefault(); update({ q: queryText.trim() || null, page: null }); }}
        style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 8 }}>
        <input type="search" aria-label="Szukaj wydarzenia" placeholder="Szukaj w nazwie i opisie…" value={queryText}
          onChange={(event) => setQueryText(event.target.value)} style={{ padding: "4px 8px" }} />
        <button type="submit" className="button">Szukaj</button>
        <span style={{ color: "#64748b" }}>{isLoading ? "Wczytuję…" : `${total} wydarzeń`}</span>
      </form>
      {error && <p role="alert" style={{ color: "#a33" }}>{error}</p>}
      {!isLoading && !error && rows.length === 0 && <p style={{ color: "#667" }}>Brak wydarzeń.</p>}
      <ul aria-label="Wydarzenia" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {rows.map((row) => (
          <li key={row.name.toLowerCase()} style={{ padding: "8px 10px", marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
            <strong>📅 {row.name}</strong>{" "}
            <span style={{ color: "#64748b", fontSize: "0.85em" }}>{row.document_count} dok. · {row.mentions} wzmianek</span>
            <div style={{ margin: "4px 0", color: row.description ? undefined : "#94a3b8" }}>
              {row.description || "Brak opisu — otwórz dokument i kliknij nazwę wydarzenia."}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, fontSize: "0.85em" }}>
              {row.documents.map((document) => (
                <Link key={document.entity_id} to={`/ner/${document.id}`}>
                  {document.title || `Dokument ${document.id}`} ×{document.mentions}
                </Link>
              ))}
            </div>
          </li>
        ))}
      </ul>
      <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading} label="wydarzeń"
        onPageChange={(next) => update({ page: next > 1 ? String(next) : null })} />
    </div>
  );
};

export default WorldEvents;
