import React from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

type Decision = {
  id: number; document_id: number | null; document_title: string | null; document_type: string | null;
  entity_type: string; entity_text: string; predicted_class: string; confidence: string;
  rationale: string | null; context_excerpt: string | null; model: string; dropped: boolean; created_at: string;
};
type Result = { total: number; items: Decision[]; summary: { total: number; dropped: number; by_class: Record<string, number> } };
const choices: Record<string, string[]> = {
  entity_type: ["persName", "placeName"],
  predicted_class: ["place", "not_place", "organization", "person", "not_person", "uncertain"],
  confidence: ["high", "medium", "low"],
};
const labels: Record<string, string> = { entity_type: "Typ encji", predicted_class: "Werdykt", confidence: "Pewność" };

export default function NerDecisions() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [search, setSearch] = useSearchParams();
  const [result, setResult] = React.useState<Result | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const rawPage = Number(search.get("page") ?? 1);
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const rawSize = Number(search.get("pageSize") ?? 50);
  const pageSize = PAGE_SIZES.includes(rawSize) ? rawSize : 50;
  const query = search.toString();
  const update = (name: string, value: string) => {
    const next = new URLSearchParams(search);
    if (value) next.set(name, value); else next.delete(name);
    if (name !== "page") next.set("page", "1");
    setSearch(next);
  };
  React.useEffect(() => {
    let active = true;
    const url = new URLSearchParams(query);
    const params: Record<string, string | number> = { limit: pageSize, offset: (page - 1) * pageSize,
      latest_only: url.get("latest_only") ?? "true" };
    for (const name of ["entity_type", "predicted_class", "confidence", "dropped", "q", "document_id"]) {
      if (url.get(name)) params[name] = url.get(name)!;
    }
    setLoading(true); setError(""); setResult(null);
    axios.get(`${apiUrl}/ner_context_decisions`, { params, headers: { "x-api-key": apiKey ?? "" } })
      .then(response => { if (active) setResult(response.data); })
      .catch(() => { if (active) setError("Nie udało się pobrać decyzji NER."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [query, page, pageSize, apiUrl, apiKey]);
  const cell: React.CSSProperties = { padding: 8, borderBottom: "1px solid #e2e8f0", textAlign: "left", verticalAlign: "top" };
  return <div>
    <h2>Automatyczne decyzje NER</h2>
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
      {Object.entries(choices).map(([name, options]) => <label key={name}>{labels[name]}{" "}
        <select value={search.get(name) ?? ""} onChange={e => update(name, e.target.value)}>
          <option value="">Wszystkie</option>{options.map(value => <option key={value}>{value}</option>)}
        </select></label>)}
      <label><input type="checkbox" checked={search.get("dropped") === "true"}
        onChange={e => update("dropped", e.target.checked ? "true" : "")} /> tylko odrzucone (dropped)</label>
      <label><input type="checkbox" checked={search.get("latest_only") !== "false"}
        onChange={e => update("latest_only", String(e.target.checked))} /> tylko najnowsze</label>
      <label>Szukaj encji <input value={search.get("q") ?? ""} onChange={e => update("q", e.target.value)} /></label>
      <label>ID dokumentu <input type="number" min="1" value={search.get("document_id") ?? ""}
        onChange={e => update("document_id", e.target.value)} /></label>
      <label>Na stronę <select value={pageSize} onChange={e => update("pageSize", e.target.value)}>
        {PAGE_SIZES.map(size => <option key={size}>{size}</option>)}
      </select></label>
    </div>
    {loading && <p>Ładowanie decyzji…</p>}
    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    {result && <>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {Object.entries({ "Łącznie": result.summary.total, "Odrzucone": result.summary.dropped, ...result.summary.by_class })
          .map(([label, count]) => <div key={label} style={{ padding: 12, border: "1px solid #cbd5e1", borderRadius: 8 }}>
            {label}: <strong>{count}</strong></div>)}
      </div>
      {!result.items.length ? <p>Brak decyzji dla wybranych filtrów.</p> : <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 10 }}>
          <thead><tr>{["Encja", "Werdykt", "Uzasadnienie", "Kontekst", "Dokument", "Model", "Data"]
            .map(label => <th key={label} style={cell}>{label}</th>)}</tr></thead>
          <tbody>{result.items.map(item => <tr key={item.id}>
            <td style={cell}>{item.entity_text}<br/><small>{item.entity_type}</small></td>
            <td style={cell}>{item.predicted_class}<br/>{item.confidence}{item.dropped && <div><span
              style={{ background: "#fee2e2", borderRadius: 4, padding: "2px 5px" }}>odrzucone</span></div>}</td>
            <td style={cell}>{item.rationale ?? "—"}</td>
            <td style={cell}>{item.context_excerpt ? <details><summary>Pokaż kontekst</summary>
              <p style={{ whiteSpace: "pre-wrap" }}>{item.context_excerpt}</p></details> : "—"}</td>
            <td style={cell}>{item.document_id != null ? <Link to={`/read/${item.document_id}`}>
              {item.document_title || `#${item.document_id}`}</Link> : "—"}</td>
            <td style={cell}>{item.model}</td><td style={cell}>{item.created_at?.replace("T", " ").slice(0, 19)}</td>
          </tr>)}</tbody>
        </table></div>}
      <Pagination page={page} pageSize={pageSize} total={result.total} isLoading={loading} label="decyzji NER"
        onPageChange={next => update("page", String(next))} />
    </>}
  </div>;
}
