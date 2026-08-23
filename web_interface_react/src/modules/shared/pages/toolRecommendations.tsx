import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

type RecommendationStatus = "watchlist" | "compare" | "testing" | "adopted" | "rejected" | "archived";
type Recommendation = {
  id: number; name: string; homepage_url: string | null; description: string | null;
  category: string | null; status: RecommendationStatus; personal_note: string | null;
  source_url: string | null; source_context: string | null;
  source_document: { title: string | null; url: string | null; discovery_source: string | null } | null;
};

const tabs: Array<[RecommendationStatus | "all", string]> = [
  ["watchlist", "Obserwowane"], ["compare", "Do porównania"], ["testing", "Testowane"],
  ["adopted", "Używane"], ["rejected", "Odrzucone"], ["archived", "Archiwum"], ["all", "Wszystkie"],
];
const nextStatuses: Array<[RecommendationStatus, string]> = [
  ["watchlist", "Obserwuj"], ["compare", "Porównaj"], ["testing", "Testuj"],
  ["adopted", "Używam"], ["rejected", "Odrzuć"], ["archived", "Archiwizuj"],
];

export default function ToolRecommendations() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [status, setStatus] = React.useState<RecommendationStatus | "all">("watchlist");
  const [items, setItems] = React.useState<Recommendation[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState<number | null>(null);
  const [importUrl, setImportUrl] = React.useState("");
  const [importMessage, setImportMessage] = React.useState("");
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "", "Content-Type": "application/json" }), [apiKey]);

  const load = React.useCallback(async () => {
    setLoading(true); setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations?status=${status}`, { headers });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(data.message || "Nie udało się pobrać radaru narzędzi"));
      setItems(Array.isArray(data.tool_recommendations) ? data.tool_recommendations as Recommendation[] : []);
    } catch (cause) {
      setError(cause instanceof TypeError ? `Nie można połączyć się z API ${apiUrl}.` : cause instanceof Error ? cause.message : "Nie udało się pobrać radaru.");
    } finally { setLoading(false); }
  }, [apiUrl, headers, status]);

  React.useEffect(() => { void load(); }, [load]);

  const move = async (item: Recommendation, nextStatus: RecommendationStatus) => {
    setBusy(item.id); setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/${item.id}/status`, {
        method: "POST", headers, body: JSON.stringify({ status: nextStatus }),
      });
      if (!response.ok) throw new Error("Nie udało się zmienić statusu rekomendacji");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Akcja nie powiodła się"); }
    finally { setBusy(null); }
  };

  const importMarkdown = async () => {
    if (!importUrl.trim()) return;
    setError(""); setImportMessage("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/import_markdown`, {
        method: "POST", headers, body: JSON.stringify({ source_url: importUrl.trim() }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(data.message || "Nie udało się zaimportować listy"));
      setImportMessage(`Zaimportowano: ${data.created}; pominięto istniejące: ${data.skipped}.`);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Import nie powiódł się"); }
  };

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <div><h1 style={{ color: "#0c2f4a", margin: 0 }}>Radar narzędzi</h1><p style={{ color: "#64748b", marginBottom: 0 }}>Ciekawe rekomendacje z zachowaną proweniencją — zanim staną się Twoimi narzędziami.</p></div>
      <button className="button" type="button" onClick={() => void load()} disabled={loading}>Odśwież</button>
    </div>
    <div role="tablist" aria-label="Status rekomendacji" style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "18px 0" }}>
      {tabs.map(([value, label]) => <button key={value} role="tab" aria-selected={status === value} className={status === value ? "button" : ""} onClick={() => setStatus(value)}>{label}</button>)}
    </div>
    <div style={{ display: "flex", alignItems: "end", gap: 8, flexWrap: "wrap", padding: "12px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, marginBottom: 18 }}>
      <label style={{ flex: "1 1 420px" }}>Importuj katalog GitHub (README Markdown)<input value={importUrl} onChange={event => setImportUrl(event.target.value)} placeholder="https://github.com/AwesomeHomelab/awesome-homelab" style={{ width: "100%", display: "block", marginTop: 4 }} /></label>
      <button className="button" disabled={!importUrl.trim()} onClick={() => void importMarkdown()}>Importuj</button>
      {importMessage && <span role="status" style={{ color: "#166534" }}>{importMessage}</span>}
    </div>
    {error && <p className="errorText" role="alert">{error}</p>}
    {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
    {!loading && !error && !items.length && <p>Brak rekomendacji w tym widoku. Dodaj kandydata przez „Do radaru”.</p>}
    {items.map(item => <article key={item.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
      <h3 style={{ marginTop: 0 }}>{item.name}</h3>
      {item.category && <span style={{ background: "#e2e8f0", color: "#334155", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>{item.category}</span>}
      {item.description && <blockquote style={{ margin: "10px 0", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 12 }}>{item.description}</blockquote>}
      {item.homepage_url && <div><a href={item.homepage_url} target="_blank" rel="noreferrer">Strona narzędzia</a></div>}
      {(item.source_document || item.source_url) && <div style={{ color: "#64748b", fontSize: ".85rem", margin: "8px 0" }}>Polecone przez: {item.source_document?.discovery_source || "źródło zewnętrzne"}{item.source_context ? ` · ${item.source_context}` : item.source_document?.title ? ` · ${item.source_document.title}` : ""}{(item.source_document?.url || item.source_url) && <> · <a href={item.source_document?.url || item.source_url || "#"} target="_blank" rel="noreferrer">źródło</a></>}</div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>{nextStatuses.filter(([value]) => value !== item.status).map(([value, label]) => <button key={value} disabled={busy === item.id} onClick={() => void move(item, value)}>{label}</button>)}</div>
    </article>)}
  </section>;
}
