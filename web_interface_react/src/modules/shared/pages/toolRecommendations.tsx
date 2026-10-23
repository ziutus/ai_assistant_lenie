import React from "react";
import { useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import ToolRelations, { type ToolRelation } from "../components/ToolRelations/toolRelations";
import ToolFocusReview from "../components/ToolFocusReview/toolFocusReview";

type RecommendationStatus = "watchlist" | "compare" | "testing" | "adopted" | "rejected" | "archived";
type GithubStats = {
  full_name: string; status: "ok" | "not_found";
  stars: number | null; forks: number | null; watchers: number | null; open_issues: number | null;
  language: string | null; license: string | null; archived: boolean;
  pushed_at: string | null; fetched_at: string | null;
};
type GithubRefreshResult = { repositories?: number; refreshed?: number; failed?: number; rate_limited?: boolean; pending?: number };
type Recommendation = {
  id: number; name: string; homepage_url: string | null; description: string | null;
  github: GithubStats | null;
  relations: ToolRelation[]; stack_matches: string[];
  feed_mentions: { count: number; samples: Array<{ id: number; title: string; url: string }> };
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

const countFormat = new Intl.NumberFormat("pl-PL");
const formatCount = (value: number | null) => value === null ? "—" : countFormat.format(value);
const INACTIVE_AFTER_MS = 365 * 24 * 60 * 60 * 1000;

function GithubStatsLine({ stats }: { stats: GithubStats }) {
  const pushed = stats.pushed_at ? Date.parse(stats.pushed_at) : NaN;
  const inactive = !Number.isNaN(pushed) && Date.now() - pushed > INACTIVE_AFTER_MS;
  const badge = (text: string, background: string, color: string) =>
    <span style={{ marginLeft: 6, background, color, borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>{text}</span>;
  return <div title={`Dane z GitHuba (${stats.full_name}), pobrane ${stats.fetched_at ? stats.fetched_at.slice(0, 10) : "—"}`}
    style={{ color: "#475569", fontSize: ".85rem", margin: "6px 0" }}>
    <span aria-label="gwiazdki">★ {formatCount(stats.stars)}</span>
    {" · "}<span aria-label="forki">⑂ {formatCount(stats.forks)}</span>
    {" · "}<span aria-label="obserwujący">👁 {formatCount(stats.watchers)}</span>
    {" · "}<span aria-label="otwarte issues">issues {formatCount(stats.open_issues)}</span>
    {stats.language && <>{" · "}{stats.language}</>}
    {stats.license && <>{" · "}{stats.license}</>}
    {stats.pushed_at && <>{" · "}ostatni push {stats.pushed_at.slice(0, 10)}</>}
    {stats.status === "not_found" && badge("repozytorium nie istnieje", "#fee2e2", "#991b1b")}
    {stats.archived && badge("zarchiwizowane", "#fef3c7", "#92400e")}
    {inactive && !stats.archived && badge("brak aktywności od ponad roku", "#fef3c7", "#92400e")}
  </div>;
}

const tabHelp: Record<RecommendationStatus | "all", string> = {
  watchlist: "Nieocenione: nowe rekomendacje, którym jeszcze nie nadano etapu. " + statusHelp.watchlist,
  compare: "Do porównania: " + statusHelp.compare,
  testing: "Testowane: " + statusHelp.testing,
  adopted: "Używane: " + statusHelp.adopted,
  rejected: "Odrzucone: " + statusHelp.rejected,
  archived: "Archiwum: " + statusHelp.archived,
  all: "Wszystkie: wpisy ze wszystkich etapów radaru naraz.",
};

function Help({ text }: { text: string }) {
  return <span role="img" tabIndex={0} title={text} aria-label={text}
    style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 16, height: 16, marginLeft: 4, borderRadius: "50%", background: "#e2e8f0", color: "#334155", fontSize: ".7rem", fontWeight: 700, cursor: "help", flex: "none" }}>?</span>;
}

export default function ToolRecommendations() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
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
  const [githubBusy, setGithubBusy] = React.useState(false);
  const [githubMessage, setGithubMessage] = React.useState("");
  const [skippedItems, setSkippedItems] = React.useState<Array<{ name: string; reason?: string }>>([]);
  const [stackOnly, setStackOnly] = React.useState(false);
  const [relationsBusy, setRelationsBusy] = React.useState(false);
  // The tool under review lives in the URL (?tool=ID), so the card can be shared and reloaded.
  const focusId = Number(searchParams.get("tool")) || null;
  const [outsideItem, setOutsideItem] = React.useState<Recommendation | null>(null);
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

  const move = async (item: Recommendation, nextStatus: RecommendationStatus, note: string | null = null): Promise<boolean> => {
    setBusy(item.id); setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/${item.id}/status`, {
        method: "POST", headers, body: JSON.stringify({ status: nextStatus, ...(note !== null ? { personal_note: note } : {}) }),
      });
      if (!response.ok) throw new Error("Nie udało się zmienić statusu rekomendacji");
      setSelectedIds(current => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
      await load();
      return true;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Akcja nie powiodła się"); return false; }
    finally { setBusy(null); }
  };

  const toggle = (id: number) => setSelectedIds(current => {
    const next = new Set(current);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  const detectRelations = async () => {
    setRelationsBusy(true); setError(""); setGithubMessage("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/relations/detect`, {
        method: "POST", headers, body: JSON.stringify({ status }),
      });
      const data = await response.json().catch(() => ({})) as { checked?: number; proposed?: Array<{ related: string[] }>; message?: string };
      if (!response.ok) throw new Error(String(data.message || "Nie udało się wykryć powiązań"));
      const total = (data.proposed ?? []).reduce((sum, entry) => sum + entry.related.length, 0);
      setGithubMessage(`Powiązania: sprawdzono ${data.checked ?? 0} wpisów, nowych propozycji: ${total}.`);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Wykrywanie powiązań nie powiodło się"); }
    finally { setRelationsBusy(false); }
  };

  const reviewRelation = async (id: number, relationStatus: "confirmed" | "rejected") => {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_relations/${id}`, { method: "PATCH", headers, body: JSON.stringify({ status: relationStatus }) });
      if (!response.ok) throw new Error("Nie udało się zapisać decyzji o powiązaniu");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Akcja nie powiodła się"); }
  };

  const stackFiltered = stackOnly ? items.filter(item => item.stack_matches.length > 0) : items;
  const visibleItems = showSelected ? stackFiltered.filter(item => selectedIds.has(item.id)) : stackFiltered;
  const setFocus = (id: number | null) => {
    setSearchParams(previous => {
      const next = new URLSearchParams(previous);
      if (id === null) next.delete("tool"); else next.set("tool", String(id));
      return next;
    });
    if (id !== null) window.scrollTo({ top: 0 });
  };
  const focusIdx = focusId === null ? -1 : visibleItems.findIndex(item => item.id === focusId);
  const focusItem = focusId === null ? undefined
    : focusIdx >= 0 ? visibleItems[focusIdx] : outsideItem?.id === focusId ? outsideItem : undefined;

  // A shared link may point at a tool that is not in the current tab or filters: fetch it on its own.
  React.useEffect(() => {
    if (focusId === null || loading || items.some(item => item.id === focusId)) { setOutsideItem(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/tool_recommendations?status=all&id=${focusId}`, { headers });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(String(data.message || "Nie udało się pobrać narzędzia"));
        const found = Array.isArray(data.tool_recommendations) ? data.tool_recommendations[0] as Recommendation | undefined : undefined;
        if (!cancelled) { setOutsideItem(found ?? null); if (!found) setError("Nie znaleziono takiego narzędzia w radarze."); }
      } catch (cause) { if (!cancelled) setError(cause instanceof Error ? cause.message : "Nie udało się pobrać narzędzia"); }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, focusId, headers, items, loading]);

  const decideFocused = async (nextStatus: RecommendationStatus, note: string | null) => {
    if (!focusItem) return;
    // Decide first which tool comes next: after the move the decided entry may leave this tab's list.
    const nextId = focusIdx >= 0 ? (visibleItems[focusIdx + 1]?.id ?? visibleItems[focusIdx - 1]?.id ?? null) : focusItem.id;
    const moved = await move(focusItem, nextStatus, note);
    if (moved) setFocus(nextId);
  };
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

  const refreshGithub = async () => {
    setGithubBusy(true); setError(""); setGithubMessage("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/github_stats/refresh`, {
        method: "POST", headers, body: JSON.stringify({ status }),
      });
      const data = await response.json().catch(() => ({})) as GithubRefreshResult & Record<string, unknown>;
      if (!response.ok) throw new Error(String(data.message || "Nie udało się pobrać danych z GitHuba"));
      const pending = data.pending ?? 0;
      setGithubMessage(`GitHub: pobrano ${data.refreshed ?? 0}${data.failed ? `, błędy: ${data.failed}` : ""}${data.rate_limited ? ". Limit zapytań GitHuba wyczerpany — spróbuj za godzinę" : pending ? `. Zostało do pobrania: ${pending} — kliknij ponownie` : ". Wszystko aktualne"}.`);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Pobieranie danych z GitHuba nie powiodło się"); }
    finally { setGithubBusy(false); }
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

  const cardDetails = (item: Recommendation) => <>
    {item.category && <span style={{ background: "#e2e8f0", color: "#334155", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>{item.category}</span>}
    {item.origin === "ai_detected" && <span style={{ marginLeft: 6, background: "#fef3c7", color: "#92400e", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>wykryte przez AI<Help text="Narzędzie wykrył model Bielik w tekście dokumentu; wymaga Twojej oceny." /></span>}
    {item.description && <blockquote style={{ margin: "10px 0", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 12 }}>{item.description}</blockquote>}
    {item.homepage_url && <div><a href={item.homepage_url} target="_blank" rel="noreferrer">Strona narzędzia</a></div>}
    {item.github && <GithubStatsLine stats={item.github} />}
    {item.feed_mentions.count > 0 && <div style={{ margin: "6px 0", color: "#475569", fontSize: ".85rem" }}
      title={item.feed_mentions.samples.map(sample => sample.title).join(", ")}>
      📰 {item.feed_mentions.count} {item.feed_mentions.count === 1 ? "wzmianka" : "wzmianek"} w feedach
      <Help text="Tyle wpisów w obserwowanych feedach (tytuł lub streszczenie) wspomina to narzędzie — sygnał, jak głośno o nim jest. Najedź na wiersz, żeby zobaczyć kilka tytułów." />
    </div>}
    {item.stack_matches.length > 0 && <div style={{ margin: "6px 0", color: "#166534", fontSize: ".85rem" }}>Dotyczy Twojego stacku: <strong>{item.stack_matches.join(", ")}</strong></div>}
    <ToolRelations relations={item.relations} onReview={(id, relationStatus) => void reviewRelation(id, relationStatus)} />
    {item.evidences.length > 0 ? <details style={{ color: "#64748b", fontSize: ".85rem", margin: "10px 0" }}>
      <summary style={{ cursor: "help" }} title="Katalogi lub dokumenty, w których to narzędzie wystąpiło, wraz z kontekstem.">Dlaczego jest w radarze? ({item.evidences.length})</summary>
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
  </>;

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <div><h1 style={{ color: "#0c2f4a", margin: 0 }}>Radar narzędzi</h1><p style={{ color: "#64748b", marginBottom: 0 }}>Ciekawe rekomendacje z zachowaną proweniencją — zanim staną się Twoimi narzędziami.</p></div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => void refreshGithub()} disabled={githubBusy || loading} title="Pobiera gwiazdki, forki i aktywność z publicznego API GitHuba dla wpisów z bieżącej zakładki (do 30 repozytoriów na raz)">{githubBusy ? "Pobieram z GitHuba…" : "Odśwież dane GitHuba"}</button>
        <button type="button" onClick={() => void detectRelations()} disabled={relationsBusy || loading} title="Szuka w tekście źródłowym każdego wpisu nazw narzędzi, które już są w radarze (np. AWS, GCP, Terraform), i proponuje powiązania do potwierdzenia. Narzędzia oznaczone jako „Używam” tworzą Twój stack.">{relationsBusy ? "Szukam powiązań…" : "Wykryj powiązania"}</button>
        <button type="button" onClick={() => setFocus(focusId !== null ? null : visibleItems[0]?.id ?? null)} disabled={loading || (focusId === null && !visibleItems.length)} title="Pokazuje narzędzia z bieżącej zakładki i filtrów pojedynczo, razem z innymi narzędziami z tej samej kategorii (także tym, którego już używasz), żeby ocenić jedno po drugim.">{focusId !== null ? "Wróć do listy" : "Oceniaj po kolei"}</button>        <button className="button" type="button" onClick={() => void load()} disabled={loading}>Odśwież</button>
      </div>
    </div>
    {githubMessage && <p role="status" style={{ color: "#166534", margin: "8px 0 0" }}>{githubMessage}</p>}
    <div role="tablist" aria-label="Status rekomendacji" style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "18px 0" }}>
      {tabs.map(([value, label]) => <button key={value} role="tab" aria-selected={status === value} title={tabHelp[value]} className={status === value ? "button" : ""} onClick={() => setStatus(value)}>{label}</button>)}
      <Help text="Etapy radaru: rekomendacja przechodzi od Nieocenionych przez Do porównania i Testowane do Używanych (albo Odrzuconych / Archiwum). Najedź na „?” przy zakładce lub przycisku, żeby zobaczyć, co oznacza." />
    </div>
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "0 0 18px" }}>Kategoria:<Help text="Filtruje po kategorii narzędzia (np. monitoring, backup) nadanej przy imporcie katalogu lub wykryciu przez AI." />
      <select value={category} onChange={event => setCategory(event.target.value)}>
        <option value="">Wszystkie kategorie</option>
        {categories.map(value => <option key={value} value={value}>{value}</option>)}
      </select>
    </label>
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "0 0 18px 12px" }}>Wejście:<Help text="Skąd wpis trafił do radaru: „Katalogi i ręczne” — zaimportowane z katalogu GitHub lub dodane ręcznie; „Wykryte przez AI” — Bielik wykrył narzędzie w tekście dokumentu." />
      <select value={origin} onChange={event => setOrigin(event.target.value as "all" | "ai_detected" | "curated")}>
        <option value="all">Wszystkie</option><option value="curated">Katalogi i ręczne</option><option value="ai_detected">Wykryte przez AI</option>
      </select>
    </label>
    <label style={{ display: "inline-flex", alignItems: "center", gap: 6, margin: "0 0 18px 12px" }}>
      <input type="checkbox" checked={stackOnly} onChange={event => setStackOnly(event.target.checked)} />Tylko pasujące do mojego stacku
      <Help text="Pokazuje wpisy powiązane z narzędziami, które masz w etapie „Używane” (np. AWS, GCP, Terraform). Powiązania wykrywa przycisk „Wykryj powiązania”." />
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
      <label style={{ flex: "2 1 420px" }}><span style={{ display: "inline-flex", alignItems: "center" }}>Importuj katalog GitHub (README Markdown)<Help text="Wklej adres repozytorium GitHub z listą narzędzi (np. awesome-list). Lenie pobierze README i doda każdą pozycję jako rekomendację; narzędzia już obecne w radarze lub Spisie narzędzi są pomijane." /></span><input value={importUrl} onChange={event => setImportUrl(event.target.value)} placeholder="https://github.com/AwesomeHomelab/awesome-homelab" style={{ width: "100%", display: "block", marginTop: 4 }} /></label>
      <label style={{ flex: "1 1 220px" }}><span style={{ display: "inline-flex", alignItems: "center" }}>Nadpisz źródło linkiem Lenie (opcjonalnie)<Help text="Dokument w Lenie (ID lub /link/10333), który poleca ten katalog — zapisze się jako „polecone przez”. Zwykle wykrywane automatycznie z adresu katalogu." /></span><input value={recommendationSource} onChange={event => setRecommendationSource(event.target.value)} placeholder="Zwykle wykrywane automatycznie" title="Importer najpierw szuka adresu katalogu w Lenie. Podaj ID lub link tylko, gdy chcesz wskazać inne źródło." style={{ width: "100%", display: "block", marginTop: 4 }} /></label>
      <button className="button" disabled={!importUrl.trim()} onClick={() => void importMarkdown()}>Importuj</button>
      {importMessage && <span role="status" style={{ color: "#166534" }}>{importMessage}</span>}
    </div>
    {skippedItems.length > 0 && <details open style={{ margin: "-8px 0 18px", padding: "10px 12px", background: "#fffbeb", border: "1px solid #fcd34d", borderRadius: 8, color: "#92400e" }}>
      <summary>Pomijane pozycje ({skippedItems.length})</summary>
      <ul style={{ margin: "8px 0 0", paddingLeft: 20 }}>{skippedItems.map(item => <li key={item.name}>{item.name} — {item.reason === "already_in_tools" ? "jest już w Spisie narzędzi" : "jest już w Radarze"}</li>)}</ul>
    </details>}
    {!loading && focusId === null && items.length > 0 && <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", margin: "0 0 16px", padding: "10px 12px", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 8 }}>
      <button type="button" onClick={selectVisible}>Zaznacz wszystkie widoczne ({visibleItems.length})</button>
      <button type="button" onClick={() => setSelectedIds(new Set())} disabled={!selectedIds.size}>Wyczyść zaznaczenie</button>
      <strong>{selectedIds.size} zaznaczonych</strong>
      <Help text="Zaznacz wpisy polami wyboru przy nazwach, żeby przenieść wiele rekomendacji do jednego etapu naraz. „Pokaż tylko zaznaczone” zawęża listę do wybranych." />
      <button type="button" disabled={!selectedIds.size} onClick={() => setShowSelected(current => !current)}>{showSelected ? "Pokaż wszystkie" : "Pokaż tylko zaznaczone"}</button>
      <label>Przenieś do:
        <select value={bulkStatus} onChange={event => setBulkStatus(event.target.value as RecommendationStatus)} style={{ marginLeft: 6 }}>
          {nextStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <button className="button" type="button" disabled={!selectedIds.size || bulkBusy} title={statusHelp[bulkStatus]} onClick={() => void applyBulkStatus()}>Zastosuj do zaznaczonych</button>
    </div>}
    {error && <p className="errorText" role="alert">{error}</p>}
    {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
    {!loading && !error && focusId === null && !items.length && <p>Brak rekomendacji w tym widoku. Zaimportuj katalog albo poczekaj na wykrycie narzędzi przez AI.</p>}
    {!loading && !error && focusId === null && items.length > 0 && !visibleItems.length && <p>Żaden z zaznaczonych wpisów nie pasuje do bieżących filtrów.</p>}
    {focusItem && <ToolFocusReview key={focusItem.id} apiUrl={apiUrl} headers={headers} itemId={focusItem.id} itemName={focusItem.name}
      initialNote={focusItem.personal_note} position={focusIdx + 1} total={visibleItems.length} busy={busy !== null}
      actions={nextStatuses.filter(([value]) => value !== focusItem.status).map(([value, label]) => [value, label, statusHelp[value]])}
      details={cardDetails(focusItem)} onDecide={(next, note) => void decideFocused(next, note)}
      onOpenPeer={id => setFocus(id)} onChanged={() => void load()}
      onPrev={() => setFocus(visibleItems[Math.max(focusIdx - 1, 0)]?.id ?? null)}
      onNext={() => setFocus(visibleItems[Math.min(focusIdx + 1, visibleItems.length - 1)]?.id ?? null)}
      onClose={() => setFocus(null)} />}
    {focusId === null && visibleItems.map(item => <article key={item.id} style={{ border: selectedIds.has(item.id) ? "2px solid #2563eb" : "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}><input type="checkbox" checked={selectedIds.has(item.id)} onChange={() => toggle(item.id)} aria-label={`Zaznacz ${item.name}`} /><h3 style={{ margin: 0 }}><button type="button" onClick={() => setFocus(item.id)} title="Otwórz to narzędzie do oceny: opis, źródła i inne narzędzia z tej kategorii" style={{ all: "unset", cursor: "pointer", color: "#1d4ed8", textDecoration: "underline" }}>{item.name}</button></h3><button type="button" onClick={() => setFocus(item.id)} title="Otwórz to narzędzie do oceny: opis, źródła i inne narzędzia z tej kategorii">Oceń</button></div>
      {cardDetails(item)}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>{nextStatuses.filter(([value]) => value !== item.status).map(([value, label]) => <button key={value} title={statusHelp[value]} aria-label={`${label}: ${statusHelp[value]}`} disabled={busy === item.id} onClick={() => void move(item, value)}>{label}</button>)}</div>
    </article>)}
  </section>;
}
