import React from "react";
import { useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

type RecommendationStatus = "watchlist" | "compare" | "testing" | "adopted" | "rejected" | "archived";
type Recommendation = {
  id: number; name: string; homepage_url: string | null; description: string | null;
  category: string | null; status: RecommendationStatus; personal_note: string | null;
  origin: "ai_detected" | "curated";
  source_url: string | null; source_context: string | null;
  source_document: { title: string | null; url: string | null; discovery_source: string | null } | null;
  evidences: Array<{
    id: number; relation_type: string; catalog_url: string | null; catalog_label: string | null; context: string | null;
    recommender_document: { id: number; title: string | null; url: string | null; discovery_source: string | null } | null;
  }>;
};
type ImportResult = { created?: number; skipped?: number; tools_skipped?: number; linked_existing?: number; evidence_created?: number; evidence_upgraded?: number; skipped_items?: Array<{ name?: string; reason?: string }>; resolved_source_document?: { id: number; title: string | null; discovery_source: string | null } | null };

const tabs: Array<[RecommendationStatus | "all", string]> = [
  ["watchlist", "Nieocenione"], ["compare", "Do porównania"], ["testing", "Testowane"],
  ["adopted", "Używane"], ["rejected", "Odrzucone"], ["archived", "Archiwum"], ["all", "Wszystkie"],
];
const nextStatuses: Array<[RecommendationStatus, string]> = [
  ["watchlist", "Obserwuj"], ["compare", "Porównaj"], ["testing", "Testuj"],
  ["adopted", "Używam"], ["rejected", "Odrzuć"], ["archived", "Archiwizuj"],
];
const statusHelp: Record<RecommendationStatus, string> = {
  watchlist: "Zachowaj jako ciekawą rekomendację na przyszłość — bez pracy teraz.",
  compare: "Zbierz alternatywy i porównaj je z obecnym rozwiązaniem, gdy pojawi się konkretny problem.",
  testing: "Uruchom lub sprawdź narzędzie w praktyce; wynik testu zdecyduje, czy trafi do używanych.",
  adopted: "Narzędzie jest już świadomie wybrane do użycia. Zostanie dodane do Spisu narzędzi, jeśli nie ma go tam jeszcze.",
  rejected: "Nie pasuje do Twoich potrzeb albo został zastąpiony innym rozwiązaniem.",
  archived: "Zachowaj historycznie, ale ukryj z bieżącego radaru.",
};

export default function ToolRecommendations() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams] = useSearchParams();
  const [status, setStatus] = React.useState<RecommendationStatus | "all">("watchlist");
  const [category, setCategory] = React.useState("");
  const [origin, setOrigin] = React.useState<"all" | "ai_detected" | "curated">(
    searchParams.get("origin") === "ai_detected" ? "ai_detected" : "all",
  );
  const [categories, setCategories] = React.useState<string[]>([]);
  const [items, setItems] = React.useState<Recommendation[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState<number | null>(null);
  const [selectedIds, setSelectedIds] = React.useState<Set<number>>(new Set());
  const [showSelected, setShowSelected] = React.useState(false);
  const [bulkStatus, setBulkStatus] = React.useState<RecommendationStatus>("compare");
  const [bulkBusy, setBulkBusy] = React.useState(false);
  const [importUrl, setImportUrl] = React.useState("");
  const [recommendationSource, setRecommendationSource] = React.useState("");
  const [importMessage, setImportMessage] = React.useState("");
  const [skippedItems, setSkippedItems] = React.useState<Array<{ name: string; reason?: string }>>([]);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "", "Content-Type": "application/json" }), [apiKey]);

  const load = React.useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ status });
      if (category) params.set("category", category);
      if (origin !== "all") params.set("origin", origin);
      const response = await fetch(`${apiUrl}/tool_recommendations?${params.toString()}`, { headers });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(data.message || "Nie udało się pobrać radaru narzędzi"));
      setItems(Array.isArray(data.tool_recommendations) ? data.tool_recommendations as Recommendation[] : []);
      setCategories(Array.isArray(data.categories) ? data.categories.filter((value: unknown): value is string => typeof value === "string") : []);
    } catch (cause) {
      setError(cause instanceof TypeError ? `Nie można połączyć się z API ${apiUrl}.` : cause instanceof Error ? cause.message : "Nie udało się pobrać radaru.");
    } finally { setLoading(false); }
  }, [apiUrl, category, headers, origin, status]);

  React.useEffect(() => { void load(); }, [load]);
  React.useEffect(() => { setSelectedIds(new Set()); }, [status, category]);
  React.useEffect(() => { if (!selectedIds.size) setShowSelected(false); }, [selectedIds]);

  const move = async (item: Recommendation, nextStatus: RecommendationStatus) => {
    setBusy(item.id); setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/${item.id}/status`, {
        method: "POST", headers, body: JSON.stringify({ status: nextStatus }),
      });
      if (!response.ok) throw new Error("Nie udało się zmienić statusu rekomendacji");
      setSelectedIds(current => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Akcja nie powiodła się"); }
    finally { setBusy(null); }
  };

  const toggle = (id: number) => setSelectedIds(current => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const visibleItems = showSelected ? items.filter(item => selectedIds.has(item.id)) : items;
  const selectVisible = () => setSelectedIds(new Set(visibleItems.map(item => item.id)));

  const applyBulkStatus = async () => {
    if (!selectedIds.size) return;
    setBulkBusy(true); setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/bulk_status`, {
        method: "POST", headers, body: JSON.stringify({ ids: Array.from(selectedIds), status: bulkStatus }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(String(data.message || "Nie udało się zmienić statusu zaznaczonych wpisów"));
      setSelectedIds(new Set());
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Masowa akcja nie powiodła się"); }
    finally { setBulkBusy(false); }
  };

  const importMarkdown = async () => {
    if (!importUrl.trim()) return;
    setError(""); setImportMessage("");
    const sourceMatch = recommendationSource.trim().match(/(?:^|\/)(\d+)(?:[/?#]|$)/);
    if (recommendationSource.trim() && !sourceMatch) {
      setError("Podaj ID dokumentu Lenie albo jego adres, np. /link/10333.");
      return;
    }
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/import_markdown`, {
        method: "POST", headers, body: JSON.stringify({
          source_url: importUrl.trim(),
          ...(sourceMatch ? { source_document_id: Number(sourceMatch[1]) } : {}),
        }),
      });
      const data = await response.json().catch(() => ({})) as ImportResult & Record<string, unknown>;
      if (!response.ok) throw new Error(String(data.message || "Nie udało się zaimportować listy"));
      const resolved = data.resolved_source_document;
      setImportMessage(`Zaimportowano: ${data.created}; pominięto istniejące: ${(data.skipped ?? 0) + (data.tools_skipped ?? 0)}; dodano relacje źródłowe: ${data.evidence_created ?? 0}.${data.evidence_upgraded ? ` Uzupełniono wcześniejsze relacje: ${data.evidence_upgraded}.` : ""}${data.linked_existing ? ` Uzupełniono źródło dla: ${data.linked_existing}.` : ""}${resolved ? ` Automatycznie rozpoznano źródło: ${resolved.discovery_source || resolved.title || `dokument ${resolved.id}`}.` : " Źródła nie znaleziono w Lenie — zapisano sam katalog zewnętrzny."}`);
      setSkippedItems(Array.isArray(data.skipped_items)
        ? data.skipped_items.filter((item): item is { name: string; reason?: string } => typeof item.name === "string")
        : []);
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
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "0 0 18px" }}>Kategoria:
      <select value={category} onChange={event => setCategory(event.target.value)}>
        <option value="">Wszystkie kategorie</option>
        {categories.map(value => <option key={value} value={value}>{value}</option>)}
      </select>
    </label>
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "0 0 18px 12px" }}>Wejście:
      <select value={origin} onChange={event => setOrigin(event.target.value as "all" | "ai_detected" | "curated")}>
        <option value="all">Wszystkie</option><option value="curated">Katalogi i ręczne</option><option value="ai_detected">Wykryte przez AI</option>
      </select>
    </label>
    <details style={{ margin: "0 0 18px", color: "#475569" }}>
      <summary style={{ cursor: "help" }}>Co znaczą etapy radaru?</summary>
      <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
        <li><strong>Obserwuj</strong> — zachowaj rekomendację na później, bez rozpoczynania researchu lub testów.</li>
        <li><strong>Porównaj</strong> — zbierz alternatywy i sprawdź, czy coś rozwiąże obecny problem lepiej.</li>
        <li><strong>Testuj</strong> — uruchom narzędzie w praktyce, zanim uznasz je za używane.</li>
        <li><strong>Używam</strong> — narzędzie zostało świadomie wybrane i trafia do Spisu narzędzi (bez duplikowania istniejącego rekordu).</li>
        <li><strong>Odrzuć</strong> — narzędzie nie pasuje do potrzeb albo lepszym wyborem jest alternatywa.</li>
        <li><strong>Archiwizuj</strong> — zachowaj wpis i jego źródła historycznie, ale ukryj go z bieżącego radaru.</li>
      </ul>
    </details>
    <div style={{ display: "flex", alignItems: "end", gap: 8, flexWrap: "wrap", padding: "12px", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, marginBottom: 18 }}>
      <label style={{ flex: "2 1 420px" }}>Importuj katalog GitHub (README Markdown)<input value={importUrl} onChange={event => setImportUrl(event.target.value)} placeholder="https://github.com/AwesomeHomelab/awesome-homelab" style={{ width: "100%", display: "block", marginTop: 4 }} /></label>
      <label style={{ flex: "1 1 220px" }}>Nadpisz źródło linkiem Lenie (opcjonalnie)<input value={recommendationSource} onChange={event => setRecommendationSource(event.target.value)} placeholder="Zwykle wykrywane automatycznie" title="Importer najpierw szuka adresu katalogu w Lenie. Podaj ID lub link tylko, gdy chcesz wskazać inne źródło." style={{ width: "100%", display: "block", marginTop: 4 }} /></label>
      <button className="button" disabled={!importUrl.trim()} onClick={() => void importMarkdown()}>Importuj</button>
      {importMessage && <span role="status" style={{ color: "#166534" }}>{importMessage}</span>}
    </div>
    {skippedItems.length > 0 && <details open style={{ margin: "-8px 0 18px", padding: "10px 12px", background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, color: "#92400e" }}>
      <summary>Pomijane pozycje ({skippedItems.length})</summary>
      <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>{skippedItems.map(item => <li key={item.name}>{item.name} — {item.reason === "already_in_tools" ? "jest już w Spisie narzędzi" : "jest już w Radarze"}</li>)}</ul>
    </details>}
    {!loading && items.length > 0 && <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", margin: "0 0 16px", padding: "10px 12px", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8 }}>
      <button type="button" onClick={selectVisible}>Zaznacz wszystkie widoczne ({visibleItems.length})</button>
      <button type="button" onClick={() => setSelectedIds(new Set())} disabled={!selectedIds.size}>Wyczyść zaznaczenie</button>
      <strong>{selectedIds.size} zaznaczonych</strong>
      <button type="button" disabled={!selectedIds.size} onClick={() => setShowSelected(current => !current)}>{showSelected ? "Pokaż wszystkie" : "Pokaż tylko zaznaczone"}</button>
      <label>Przenieś do:
        <select value={bulkStatus} onChange={event => setBulkStatus(event.target.value as RecommendationStatus)} style={{ marginLeft: 6 }}>
          {nextStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <button className="button" type="button" disabled={!selectedIds.size || bulkBusy} title={statusHelp[bulkStatus]} onClick={() => void applyBulkStatus}>Zastosuj do zaznaczonych</button>
    </div>}
    {error && <p className="errorText" role="alert">{error}</p>}
    {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
    {!loading && !error && !items.length && <p>Brak rekomendacji w tym widoku. Zaimportuj katalog albo poczekaj na wykrycie narzędzi przez AI.</p>}
    {!loading && !error && items.length > 0 && !visibleItems.length && <p>Żaden z zaznaczonych wpisów nie pasuje do bieżących filtrów.</p>}
    {visibleItems.map(item => <article key={item.id} style={{ border: selectedIds.has(item.id) ? "2px solid #2563eb" : "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}><input type="checkbox" checked={selectedIds.has(item.id)} onChange={() => toggle(item.id)} aria-label={`Zaznacz ${item.name}`} /><h3 style={{ margin: 0 }}>{item.name}</h3></div>
      {item.category && <span style={{ background: "#e2e8f0", color: "#334155", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>{item.category}</span>}
      {item.origin === "ai_detected" && <span style={{ marginLeft: 6, background: "#fef3c7", color: "#92400e", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>wykryte przez AI</span>}
      {item.description && <blockquote style={{ margin: "10px 0", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 12 }}>{item.description}</blockquote>}
      {item.homepage_url && <div><a href={item.homepage_url} target="_blank" rel="noreferrer">Strona narzędzia</a></div>}
      {item.evidences.length > 0 ? <details style={{ color: "#64748b", fontSize: ".85rem", margin: "10px 0" }}>
        <summary style={{ cursor: "help" }}>Dlaczego jest w radarze? ({item.evidences.length})</summary>
        <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>
          {item.evidences.map(evidence => <li key={evidence.id}>
            {evidence.relation_type === "mentioned_in" ? "Wspomniane w: " : "Znajduje się w katalogu: "}
            {evidence.catalog_url ? <a href={evidence.catalog_url} target="_blank" rel="noreferrer">{evidence.catalog_label || evidence.catalog_url}</a> : evidence.catalog_label || "nieznane źródło"}
            {evidence.context && ` · ${evidence.context}`}
            {evidence.recommender_document && <div style={{ marginTop: 3 }}>↳ katalog polecony przez: {evidence.recommender_document.discovery_source || evidence.recommender_document.title || "link Lenie"}{evidence.recommender_document.title && evidence.recommender_document.discovery_source ? ` · ${evidence.recommender_document.title}` : ""}{evidence.recommender_document.url && <> · <a href={evidence.recommender_document.url} target="_blank" rel="noreferrer">otwórz</a></>}</div>}
          </li>)}
        </ul>
      </details> : (item.source_document || item.source_url) && <div style={{ color: "#64748b", fontSize: ".85rem", margin: "8px 0" }}>
        {item.source_document && <div>Polecone przez: {item.source_document.discovery_source || item.source_document.title || "link Lenie"}{item.source_document.title && item.source_document.discovery_source ? ` · ${item.source_document.title}` : ""}{item.source_document.url && <> · <a href={item.source_document.url} target="_blank" rel="noreferrer">otwórz rekomendację</a></>}</div>}
        {item.source_url && <div>{item.source_document ? "Katalog: " : "Katalog źródłowy: "}<a href={item.source_url} target="_blank" rel="noreferrer">{item.source_url}</a>{item.source_context ? ` · ${item.source_context}` : ""}</div>}
      </div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>{nextStatuses.filter(([value]) => value !== item.status).map(([value, label]) => <button key={value} title={statusHelp[value]} aria-label={`${label}: ${statusHelp[value]}`} disabled={busy === item.id} onClick={() => void move(item, value)}>{label}</button>)}</div>
    </article>)}
  </section>;
}
