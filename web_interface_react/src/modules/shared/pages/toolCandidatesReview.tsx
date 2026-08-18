import React from "react";
import { useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

type ToolCandidateSourceDocument = {
  id: number;
  title: string | null;
  url: string | null;
  byline: string | null;
  discovery_source: string | null;
  published_on: string | null;
  ingested_at: string | null;
};
type ToolCandidate = {
  id: number;
  name: string;
  status: "pending" | "accepted" | "rejected" | "deferred";
  context_snippet: string | null;
  detected_by: string;
  created_at: string | null;
  reviewed_at: string | null;
  source_document_id: number;
  source_document: ToolCandidateSourceDocument;
};
type Source = { id: number; name: string; is_active: boolean };
type CandidateStatus = "pending" | "accepted" | "rejected" | "deferred";

const statusTabs: Array<[CandidateStatus, string]> = [
  ["pending", "Oczekujące"],
  ["accepted", "Zaakceptowane"],
  ["rejected", "Odrzucone"],
  ["deferred", "Odłożone"],
];

const UNKNOWN_SOURCE_LABEL = "Nieznane źródło";

export default function ToolCandidatesReview() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const [candidates, setCandidates] = React.useState<ToolCandidate[]>([]);
  const [sources, setSources] = React.useState<Source[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [busyCandidateId, setBusyCandidateId] = React.useState<number | null>(null);
  const [warningBanner, setWarningBanner] = React.useState<string | null>(null);

  const status = (searchParams.get("status") as CandidateStatus) || "pending";
  const sourceFilter = searchParams.get("source") || "";
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "" }), [apiKey]);

  const updateParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    setSearchParams(next);
  };

  const load = React.useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ status });
      if (sourceFilter) params.set("source", sourceFilter);
      const [candidatesResponse, sourcesResponse] = await Promise.all([
        fetch(`${apiUrl}/tool_candidates?${params.toString()}`, { headers }),
        fetch(`${apiUrl}/sources`, { headers }),
      ]);
      const readResponse = async (response: Response): Promise<Record<string, unknown>> => {
        const text = await response.text();
        if (!text) return {};
        try { return JSON.parse(text) as Record<string, unknown>; } catch { return { message: text }; }
      };
      const candidatesData = await readResponse(candidatesResponse);
      const sourcesData = await readResponse(sourcesResponse);
      if (!candidatesResponse.ok) {
        const detail = candidatesResponse.status === 401 || candidatesResponse.status === 403
          ? "Klucz API nie ma uprawnień do przeglądu kandydatów-narzędzi"
          : String(candidatesData.message || "Nie udało się pobrać kandydatów-narzędzi");
        throw new Error(`${detail} (HTTP ${candidatesResponse.status}, ${apiUrl}/tool_candidates)`);
      }
      if (!sourcesResponse.ok) {
        const detail = sourcesResponse.status === 401 || sourcesResponse.status === 403
          ? "Klucz API nie ma uprawnień do źródeł"
          : String(sourcesData.message || "Nie udało się pobrać źródeł");
        throw new Error(`${detail} (HTTP ${sourcesResponse.status}, ${apiUrl}/sources)`);
      }
      setCandidates(Array.isArray(candidatesData.tool_candidates) ? candidatesData.tool_candidates as ToolCandidate[] : []);
      setSources(Array.isArray(sourcesData.sources) ? sourcesData.sources as Source[] : []);
    } catch (cause) {
      setError(cause instanceof TypeError
        ? `Nie można połączyć się z API ${apiUrl}. Sprawdź adres API, CORS i połączenie z NAS-em.`
        : cause instanceof Error ? cause.message : "Nie udało się pobrać kandydatów-narzędzi");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, headers, sourceFilter, status]);

  React.useEffect(() => { void load(); }, [load]);

  const act = async (id: number, action: "accept" | "reject" | "defer") => {
    setBusyCandidateId(id);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_candidates/${id}/${action}`, {
        method: "POST", headers,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = response.status === 403
          ? "Klucz API nie ma uprawnień użytkownika do decyzji o kandydatach-narzędziach"
          : String(data.message || data.error || "Akcja nie powiodła się");
        throw new Error(`${detail} (HTTP ${response.status})`);
      }
      if (action === "accept") {
        setWarningBanner(typeof data.warning === "string" ? data.warning : null);
      }
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Akcja nie powiodła się");
    } finally {
      setBusyCandidateId(null);
    }
  };

  const groups = React.useMemo(() => {
    const map = candidates.reduce((accumulator, candidate) => {
      const key = candidate.source_document.discovery_source ?? UNKNOWN_SOURCE_LABEL;
      const list = accumulator.get(key);
      if (list) list.push(candidate); else accumulator.set(key, [candidate]);
      return accumulator;
    }, new Map<string, ToolCandidate[]>());
    return Array.from(map.entries()).sort(([sourceA], [sourceB]) => {
      if (sourceA === UNKNOWN_SOURCE_LABEL) return sourceB === UNKNOWN_SOURCE_LABEL ? 0 : 1;
      if (sourceB === UNKNOWN_SOURCE_LABEL) return -1;
      return sourceA.localeCompare(sourceB, "pl");
    });
  }, [candidates]);

  const formatDate = (value: string | null) => value ? new Date(value).toLocaleString("pl-PL") : null;

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <h1 style={{ color: "#0c2f4a" }}>Kandydaci-narzędzia</h1>
      <button className="button" type="button" onClick={() => void load()} disabled={loading}>Odśwież</button>
    </div>
    <div role="tablist" aria-label="Status kandydata" style={{ display: "flex", gap: 8, margin: "8px 0 16px" }}>
      {statusTabs.map(([value, label]) => (
        <button
          key={value}
          role="tab"
          aria-selected={status === value}
          className={status === value ? "button" : ""}
          onClick={() => updateParams({ status: value === "pending" ? null : value })}
        >
          {label}
        </button>
      ))}
    </div>
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "8px 0 20px" }}>
      Źródło:
      <select value={sourceFilter} onChange={event => updateParams({ source: event.target.value || null })} disabled={loading && sources.length === 0}>
        <option value="">Wszystkie źródła</option>
        {sources.map(source => <option key={source.id} value={source.name}>{source.name}{!source.is_active ? " (nieaktywne)" : ""}</option>)}
      </select>
    </label>
    {error && <p className="errorText" role="alert">{error}</p>}
    {warningBanner && <div role="status" style={{
      display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12,
      background: "#fffbeb", border: "1px solid #fcd34d", color: "#92400e",
      borderRadius: 8, padding: "10px 14px", marginBottom: 16,
    }}>
      <span>{warningBanner}</span>
      <button type="button" onClick={() => setWarningBanner(null)} aria-label="Zamknij ostrzeżenie">✕</button>
    </div>}
    {!loading && !error && !candidates.length && <p>Brak kandydatów dla wybranych filtrów.</p>}
    {groups.map(([sourceName, groupCandidates]) => <div key={sourceName} style={{ marginBottom: 24 }}>
      <h2 style={{ color: "#334155", fontSize: "1.1rem", borderBottom: "1px solid #e2e8f0", paddingBottom: 6 }}>
        {sourceName} ({groupCandidates.length})
      </h2>
      {groupCandidates.map(candidate => {
        const busy = busyCandidateId === candidate.id;
        const document = candidate.source_document;
        const publishedOrIngested = formatDate(document.published_on) || formatDate(document.ingested_at);
        return <article key={candidate.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
          <h3>{candidate.name}</h3>
          {candidate.context_snippet && <blockquote style={{ margin: "8px 0", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 12 }}>
            {candidate.context_snippet}
          </blockquote>}
          <div style={{ color: "#64748b", fontSize: ".85rem", marginBottom: 6 }}>
            {document.title && <span>{document.title}</span>}
            {document.byline && <span> · {document.byline}</span>}
            {document.discovery_source && <span> · {document.discovery_source}</span>}
            {publishedOrIngested && <span> · {publishedOrIngested}</span>}
          </div>
          {document.url && <div><a href={document.url} target="_blank" rel="noreferrer">{document.url}</a></div>}
          <div style={{ margin: "8px 0" }}>
            <span style={{ background: "#e2e8f0", color: "#334155", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>
              wykryto przez: {candidate.detected_by}
            </span>
          </div>
          <div>
            <button className="button" disabled={busy} onClick={() => void act(candidate.id, "accept")}>Akceptuj</button>{" "}
            <button disabled={busy} onClick={() => void act(candidate.id, "reject")}>Odrzuć</button>{" "}
            <button disabled={busy} onClick={() => void act(candidate.id, "defer")}>Odłóż</button>
          </div>
        </article>;
      })}
    </div>)}
  </section>;
}
