import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

interface InformationSource {
  id: number;
  canonical_name: string;
  source_type: string | null;
  domain: string | null;
  aliases: string[];
  document_count: number;
}

interface SourceDocument {
  document_id: number;
  title: string;
  url: string;
  role: string;
  raw_mention: string;
  evidence_excerpt: string | null;
}

interface PublisherStats {
  published_document_count: number;
  without_external_source_count: number;
  with_external_source_count: number;
  role_counts: Record<string, number>;
  origins: Array<{ source_id: number; canonical_name: string; role: string; document_count: number }>;
}

const ROLE_LABELS: Record<string, string> = {
  publisher: "publikacja",
  original_reporting: "źródło ustaleń",
  republication: "przedruk / opracowanie",
  cited: "cytowanie",
  data_source: "źródło danych",
};

const box: React.CSSProperties = {
  border: "1px solid #e2e8f0", borderRadius: 8, padding: 14, background: "#fff",
};

const InformationSources: React.FC = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [params, setParams] = useSearchParams();
  const selectedId = Number(params.get("id")) || null;
  const [query, setQuery] = React.useState(params.get("q") ?? "");
  const [sources, setSources] = React.useState<InformationSource[]>([]);
  const [documents, setDocuments] = React.useState<SourceDocument[]>([]);
  const [stats, setStats] = React.useState<PublisherStats | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const headers = React.useMemo(() => ({ "x-api-key": `${apiKey}` }), [apiKey]);

  const search = React.useCallback(async (value: string) => {
    setLoading(true); setError("");
    try {
      const response = await axios.get(`${apiUrl}/information_sources`, {
        params: value.trim() ? { q: value.trim() } : {}, headers,
      });
      setSources(response.data.entries ?? []);
    } catch (e: any) {
      setError(e.response?.data?.message || e.message);
    } finally { setLoading(false); }
  }, [apiUrl, headers]);

  React.useEffect(() => { search(params.get("q") ?? ""); }, [params, search]);

  React.useEffect(() => {
    if (!selectedId) { setDocuments([]); setStats(null); return; }
    Promise.all([
      axios.get(`${apiUrl}/information_sources/${selectedId}/documents`, { headers }),
      axios.get(`${apiUrl}/information_sources/${selectedId}/publisher_stats`, { headers }),
    ]).then(([docs, publisher]) => {
      setDocuments(docs.data.entries ?? []);
      setStats(publisher.data);
    }).catch((e: any) => setError(e.response?.data?.message || e.message));
  }, [apiUrl, headers, selectedId]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (query.trim()) next.q = query.trim();
    setParams(next);
  };
  const selected = sources.find(source => source.id === selectedId);

  return (
    <div style={{ maxWidth: 1050, margin: "0 auto", padding: 20 }}>
      <h2>Źródła informacji</h2>
      <p style={{ color: "#64748b" }}>Wyszukuj media i instytucje, z których pochodzą ustalenia, cytaty lub dane.</p>
      <form onSubmit={submit} style={{ display: "flex", gap: 8, marginBottom: 18 }}>
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="np. NYT, Reuters, BBC"
          style={{ flex: 1, padding: 9, border: "1px solid #cbd5e1", borderRadius: 6 }} />
        <button className="button" type="submit">Szukaj</button>
      </form>
      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      {loading ? <p>Ładowanie…</p> : (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(260px, 1fr) minmax(420px, 2fr)", gap: 16 }}>
          <div style={box}>
            <strong>Źródła ({sources.length})</strong>
            {sources.map(source => (
              <button key={source.id} onClick={() => {
                const next: Record<string, string> = { id: String(source.id) };
                if (params.get("q")) next.q = params.get("q")!;
                setParams(next);
              }} style={{
                display: "block", width: "100%", textAlign: "left", marginTop: 8, padding: 8,
                border: "none", borderRadius: 6, cursor: "pointer",
                background: selectedId === source.id ? "#e0f2fe" : "#f8fafc",
              }}>
                <strong>{source.canonical_name}</strong> <span style={{ color: "#64748b" }}>×{source.document_count}</span>
                {source.domain && <div style={{ fontSize: "0.8em", color: "#64748b" }}>{source.domain}</div>}
              </button>
            ))}
          </div>
          <div>
            {!selectedId && <div style={box}>Wybierz źródło, aby zobaczyć dokumenty i statystyki.</div>}
            {selectedId && <>
              <div style={box}>
                <h3 style={{ marginTop: 0 }}>{selected?.canonical_name ?? "Źródło"}</h3>
                {stats && <>
                  <strong>Jako portal publikujący</strong>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
                    <span>wszystkie: {stats.published_document_count}</span>
                    <span>z wykrytym źródłem zewnętrznym: {stats.with_external_source_count}</span>
                    <span>bez wykrytego źródła zewnętrznego: {stats.without_external_source_count}</span>
                  </div>
                  <small style={{ display: "block", color: "#64748b", marginTop: 7 }}>
                    „Bez wykrytego źródła” nie jest automatycznie dowodem własnego reportingu.
                  </small>
                  {stats.origins.length > 0 && <div style={{ marginTop: 12 }}>
                    <strong>Najczęstsze źródła zewnętrzne</strong>
                    {stats.origins.map(origin => <div key={`${origin.source_id}-${origin.role}`}>
                      <NavLink to={`/information-sources?id=${origin.source_id}`}>{origin.canonical_name}</NavLink>
                      {" — "}{ROLE_LABELS[origin.role] ?? origin.role}: {origin.document_count}
                    </div>)}
                  </div>}
                </>}
              </div>
              <div style={{ ...box, marginTop: 14 }}>
                <strong>Powiązane dokumenty ({documents.length})</strong>
                {documents.map(doc => <div key={`${doc.document_id}-${doc.role}`} style={{ padding: "10px 0", borderBottom: "1px solid #e2e8f0" }}>
                  <NavLink to={`/read/${doc.document_id}`}>{doc.title || `Dokument #${doc.document_id}`}</NavLink>
                  <div style={{ fontSize: "0.82em", color: "#64748b" }}>{ROLE_LABELS[doc.role] ?? doc.role}</div>
                  {doc.evidence_excerpt && <div style={{ fontSize: "0.86em", marginTop: 3 }}>„{doc.evidence_excerpt}”</div>}
                </div>)}
              </div>
            </>}
          </div>
        </div>
      )}
    </div>
  );
};

export default InformationSources;
