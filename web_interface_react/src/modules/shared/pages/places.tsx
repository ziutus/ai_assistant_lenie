import React from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

// Global place registry: places are stored per document (document_entities); this page groups them by name
// across all documents and lets the reviewer attach a Wikipedia article and aliases (place_profiles,
// backend/library/place_registry.py). The documents mentioning a place are the "articles linked to it".

interface PlaceProfile { id: number; canonical_name: string; wikipedia_url: string | null; aliases: string[]; note: string | null }
interface PlaceRow { key: string; name: string; documents: number; mentions: number; located: boolean; is_country: boolean; profile: PlaceProfile | null }
interface PlaceDocument { id: number; title: string | null; document_type: string; mentions: number; forms: string[] }
interface PlaceDetail { name: string; profile: PlaceProfile | null; documents: PlaceDocument[] }

const DEFAULT_PAGE_SIZE = 50;

const Places = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const withWikipedia = searchParams.get("with_wikipedia") === "1";
  const selected = searchParams.get("name") ?? "";
  const requestedPageSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const pageSize = PAGE_SIZES.includes(requestedPageSize) ? requestedPageSize : DEFAULT_PAGE_SIZE;
  const requestedPage = Number(searchParams.get("page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const [queryText, setQueryText] = React.useState(q);
  const [rows, setRows] = React.useState<PlaceRow[]>([]);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [detail, setDetail] = React.useState<PlaceDetail | null>(null);
  const [wikipediaUrl, setWikipediaUrl] = React.useState("");
  const [aliasesText, setAliasesText] = React.useState("");
  const [note, setNote] = React.useState("");
  const [saveMessage, setSaveMessage] = React.useState("");
  const [isSaving, setIsSaving] = React.useState(false);
  const [version, setVersion] = React.useState(0);
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
    axios.get(`${apiUrl}/places`, {
      headers,
      params: { q, with_wikipedia: withWikipedia ? "1" : "0", limit: pageSize, offset: (page - 1) * pageSize },
    }).then((response) => {
      if (cancelled) return;
      setRows(response.data.places ?? []);
      setTotal(response.data.total ?? 0);
    }).catch((reason: any) => {
      if (!cancelled) setError(`Nie udało się pobrać miejsc: ${reason.response?.data?.message || reason.message}`);
    }).finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [apiUrl, headers, q, withWikipedia, page, pageSize, version]);

  React.useEffect(() => setSaveMessage(""), [selected]);

  React.useEffect(() => {
    if (!selected) { setDetail(null); return; }
    let cancelled = false;
    axios.get(`${apiUrl}/places/detail`, { headers, params: { name: selected } })
      .then((response) => {
        if (cancelled) return;
        const data: PlaceDetail = response.data;
        setDetail(data);
        setWikipediaUrl(data.profile?.wikipedia_url ?? "");
        setAliasesText((data.profile?.aliases ?? []).join(", "));
        setNote(data.profile?.note ?? "");
      })
      .catch((reason: any) => {
        if (!cancelled) setError(`Nie udało się pobrać miejsca: ${reason.response?.data?.message || reason.message}`);
      });
    return () => { cancelled = true; };
  }, [apiUrl, headers, selected, version]);

  const save = async () => {
    if (!detail) return;
    setIsSaving(true);
    setSaveMessage("");
    try {
      await axios.put(`${apiUrl}/places/profile`, {
        name: detail.name,
        wikipedia_url: wikipediaUrl.trim() || null,
        aliases: aliasesText.split(/[,;]+/).map((alias) => alias.trim()).filter(Boolean),
        note: note.trim() || null,
      }, { headers });
      setSaveMessage("Zapisano.");
      setVersion((current) => current + 1);
    } catch (reason: any) {
      setSaveMessage(`Nie udało się zapisać: ${reason.response?.data?.message || reason.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Miejsca</h2>
      <p style={{ color: "#667", marginBottom: 10 }}>
        Miejsca z wszystkich dokumentów, zgrupowane po nazwie. Do miejsca możesz dodać artykuł Wikipedii i aliasy
        (np. „Yanbu” dla „Janbu”); dokumenty, które je wspominają, widać po wybraniu miejsca.
      </p>
      <form onSubmit={(event) => { event.preventDefault(); update({ q: queryText.trim() || null, page: null }); }}
        style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 8 }}>
        <input type="search" aria-label="Szukaj miejsca" placeholder="Szukaj miejsca…" value={queryText}
          onChange={(event) => setQueryText(event.target.value)} style={{ padding: "4px 8px" }} />
        <button type="submit" className="button">Szukaj</button>
        <label>
          <input type="checkbox" checked={withWikipedia}
            onChange={(event) => update({ with_wikipedia: event.target.checked ? "1" : null, page: null })} />{" "}
          Tylko z Wikipedią
        </label>
      </form>
      {error && <p role="alert" style={{ color: "#a33" }}>{error}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)", gap: 18, alignItems: "start" }}>
        <div>
          {isLoading && <p>Ładowanie…</p>}
          {!isLoading && rows.length === 0 && !error && <p>Brak miejsc.</p>}
          {rows.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left" }}><th>Miejsce</th><th>Dokumenty</th><th>Wzmianki</th><th>Wikipedia</th></tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key} style={{ background: row.key === selected.toLowerCase() ? "#eef4ff" : undefined }}>
                    <td>
                      <button type="button" onClick={() => update({ name: row.name })}
                        style={{ border: 0, background: "transparent", cursor: "pointer", color: "#1d5ca8", font: "inherit", padding: 0 }}>
                        {row.name}
                      </button>
                      {row.is_country && <span title="Państwo" style={{ marginLeft: 4 }}>🌍</span>}
                      {row.located && <span title="Zlokalizowane" style={{ marginLeft: 4, color: "#2e7d43" }}>✓</span>}
                    </td>
                    <td>{row.documents}</td>
                    <td>{row.mentions}</td>
                    <td>
                      {row.profile?.wikipedia_url
                        ? <a href={row.profile.wikipedia_url} target="_blank" rel="noopener noreferrer" aria-label={`Wikipedia: ${row.name}`}>📖</a>
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading} label="miejsc"
            onPageChange={(next) => update({ page: next === 1 ? null : String(next) })} />
        </div>
        <aside aria-label="Szczegóły miejsca">
          {!detail && <p style={{ color: "#667" }}>Wybierz miejsce z listy.</p>}
          {detail && (
            <div style={{ border: "1px solid #e2e8f0", borderRadius: 6, padding: 12, background: "#fff" }}>
              <h3 style={{ marginTop: 0 }}>{detail.name}</h3>
              {detail.profile?.wikipedia_url && (
                <p><a href={detail.profile.wikipedia_url} target="_blank" rel="noopener noreferrer">📖 Artykuł w Wikipedii</a></p>
              )}
              <label style={{ display: "block", marginBottom: 6 }}>Adres artykułu Wikipedii
                <input value={wikipediaUrl} onChange={(event) => setWikipediaUrl(event.target.value)}
                  placeholder="https://pl.wikipedia.org/wiki/…" style={{ display: "block", width: "100%" }} />
              </label>
              <label style={{ display: "block", marginBottom: 6 }}>Aliasy (po przecinku)
                <input value={aliasesText} onChange={(event) => setAliasesText(event.target.value)}
                  style={{ display: "block", width: "100%" }} />
              </label>
              <label style={{ display: "block", marginBottom: 6 }}>Notatka
                <textarea value={note} onChange={(event) => setNote(event.target.value)} rows={2}
                  style={{ display: "block", width: "100%" }} />
              </label>
              <button type="button" className="button" disabled={isSaving} onClick={() => void save()}>Zapisz</button>
              {saveMessage && <span role="status" style={{ marginLeft: 8 }}>{saveMessage}</span>}
              <h4 style={{ marginBottom: 4 }}>Dokumenty z tym miejscem ({detail.documents.length})</h4>
              {detail.documents.length === 0 && <p style={{ color: "#667" }}>Brak dokumentów.</p>}
              <ul style={{ paddingLeft: 18, margin: 0 }}>
                {detail.documents.map((document) => (
                  <li key={document.id} style={{ marginBottom: 4 }}>
                    <Link to={`/read/${document.id}`}>{document.title || `Dokument ${document.id}`}</Link>
                    <span style={{ color: "#64748b", fontSize: "0.85em" }}>
                      {" "}· {document.document_type} · ×{document.mentions}
                      {document.forms.length > 1 && ` (${document.forms.join(", ")})`}
                    </span>
                    {" "}<Link to={`/ner/${document.id}`} style={{ fontSize: "0.85em" }}>NER</Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
};

export default Places;
