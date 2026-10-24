import React from "react";
import { Pagination } from "../components/Pagination/pagination";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import ContentGroupsPanel from "../components/ContentGroupsPanel/ContentGroupsPanel";
import { loadFeedReviewFilters, saveFeedReviewFilters } from "../services/storage";
import type { ContentGroup } from "../../../types";
import OpenRouterBalance from "../components/OpenRouterBalance/openRouterBalance";
import { modelOptionText, type ModelOption } from "../utils/modelDetails";

type FeedSource = { id: number; name: string; type: string; disabled: boolean };
type FeedItem = {
  id: number;
  feed_source_id: number;
  title: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  status: string;
  saved_at: string | null;
  saved_by_user_id: number | null;
  groups?: ContentGroup[];
};

type Action = "import" | "skip" | "ignore" | "save-for-later" | "restore" | "to_radar";
type ReviewDecision = {
  id: number; batch_id: string; job_id: string | null; feed_item_id: number;
  feed_source_id: number; title: string; action: string; previous_status: string;
  new_status: string; created_at: string; undone_at: string | null;
};
type ReviewReason = "not_interested" | "duplicate" | "already_known" | "too_long" | "other";
const reviewReasons: Array<[ReviewReason, string]> = [
  ["not_interested", "Nie interesuje mnie temat"],
  ["duplicate", "Duplikat / już widziałem"],
  ["already_known", "Już to znam"],
  ["too_long", "Za długie"],
  ["other", "Inny powód"],
];

// Without a timeout a request sent while the VPN/network is down can hang for
// minutes (packets are silently dropped), leaving the button disabled and no
// message. Imports fetch the page server-side, so they get a longer budget.
const RADAR_HELP = "Do radaru: wpis trafia do Radaru narzędzi (etap „Obserwuję”) z tym materiałem jako źródłem, a stąd znika. Lenie od razu proponuje powiązania z narzędziami, które już masz w radarze (np. AWS, Terraform). Jeśli narzędzie jest już w radarze, materiał zostanie dopisany jako kolejna wzmianka.";
const RADAR_CATEGORY_HINTS = ["DecisionModels", "Development", "AI", "InfraManagement", "Security"];
const suggestToolName = (title: string) => (title.split(/\s+[-–—]\s+|\s*:\s+|\s*\|\s*/)[0] || title).trim();
const ACTION_TIMEOUT_MS = 20_000;
const IMPORT_TIMEOUT_MS = 90_000;

class RequestTimeoutError extends Error {}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (cause) {
    if (controller.signal.aborted) throw new RequestTimeoutError();
    throw cause;
  } finally {
    window.clearTimeout(timer);
  }
}

// fetch() rejects with TypeError ("Failed to fetch") when no connection could
// be opened — VPN off, Wi-Fi down, wrong API address — as opposed to an HTTP
// error the backend actually returned.
function describeActionError(cause: unknown, apiUrl: string | undefined, fallback: string): string {
  if (cause instanceof RequestTimeoutError) {
    return `Brak odpowiedzi z API ${apiUrl} — zmiana NIE została zapisana. Sprawdź połączenie (VPN) i spróbuj ponownie.`;
  }
  if (cause instanceof TypeError) {
    return `Nie można połączyć się z API ${apiUrl} — zmiana NIE została zapisana. Sprawdź połączenie (VPN) i spróbuj ponownie.`;
  }
  return cause instanceof Error ? cause.message : fallback;
}

const SKIP_HELP = "Pomiń: odrzuca tylko ten jeden wpis. Zapytam o powód (np. nie interesuje mnie, duplikat) — zostanie zapisany do przyszłej oceny preferencji.";
const IGNORE_HELP = "Ignoruj: dodaje regułę do źródła (wzorzec w tytule lub początek adresu URL). Pasujące wpisy w kolejce są od razu ignorowane, a nowe z tego źródła pomijane automatycznie.";

function HelpBadge({ text }: { text: string }) {
  return <span title={text} aria-label={text} role="img"
    style={{ cursor: "help", color: "#64748b", fontSize: ".85rem", marginRight: 6 }}>ⓘ</span>;
}

export default function FeedReview() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = React.useState<FeedItem[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(1);
  const pageSize = 50;
  const pageRef = React.useRef(1);
  const [index, setIndex] = React.useState(0);
  // A shared link (?item=<id>) can point at an item outside the loaded page/tab: it is fetched on its own and pinned.
  const initialItemRef = React.useRef(searchParams.get("item"));
  const [itemResolved, setItemResolved] = React.useState(!initialItemRef.current);
  const [pinned, setPinned] = React.useState<FeedItem | null>(null);
  const [linkMessage, setLinkMessage] = React.useState("");
  const [models, setModels] = React.useState<ModelOption[]>([]);
  const [suggestModel, setSuggestModel] = React.useState("");
  const [defaultModel, setDefaultModel] = React.useState("");
  const [modelsLoaded, setModelsLoaded] = React.useState(false);
  const [modelMessage, setModelMessage] = React.useState("");
  const [modelCalls, setModelCalls] = React.useState(0);
  const onModelCall = React.useCallback(() => setModelCalls(value => value + 1), []);
  const [sources, setSources] = React.useState<FeedSource[]>([]);
  const [contentGroups, setContentGroups] = React.useState<ContentGroup[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busyItemId, setBusyItemId] = React.useState<number | null>(null);
  const [error, setError] = React.useState("");
  const [itemError, setItemError] = React.useState<{ id: number; message: string } | null>(null);
  const [ignoreItemId, setIgnoreItemId] = React.useState<number | null>(null);
  const [ignoreField, setIgnoreField] = React.useState<"title" | "url">("title");
  const [ignorePattern, setIgnorePattern] = React.useState("");
  const [skipItemId, setSkipItemId] = React.useState<number | null>(null);
  const [skipReason, setSkipReason] = React.useState<ReviewReason>("not_interested");
  const [radarItemId, setRadarItemId] = React.useState<number | null>(null);
  const [radarName, setRadarName] = React.useState("");
  const [radarCategory, setRadarCategory] = React.useState("");
  const [radarMessage, setRadarMessage] = React.useState("");
  const [showHistory, setShowHistory] = React.useState(false);
  const [decisions, setDecisions] = React.useState<ReviewDecision[]>([]);
  const [historyLoading, setHistoryLoading] = React.useState(false);
  const [importedTypes, setImportedTypes] = React.useState<Record<number, string>>({});

  // Read on every render: choosing "Nowe" / "Wszystkie źródła" drops the URL param and falls back to the value
  // just saved by updateParams(); a copy frozen at mount kept the old tab (the "Nowe" button did nothing).
  const storedFilters = loadFeedReviewFilters();
  const selectedSource = searchParams.has("feed_source_id")
    ? searchParams.get("feed_source_id") || ""
    : storedFilters.feedSourceId;
  const view = searchParams.has("view")
    ? searchParams.get("view") === "later" ? "later" : "new"
    : storedFilters.view;
  const mode = searchParams.has("mode") ? (searchParams.get("mode") === "all" ? "all" : "single") : storedFilters.mode || "single";
  const status = view === "later" ? "saved_for_later" : "new";
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "" }), [apiKey]);

  React.useEffect(() => {
    let cancelled = false;
    setModelsLoaded(false);
    void fetchWithTimeout(`${apiUrl}/feed_items/content_group_model`, { headers }, ACTION_TIMEOUT_MS)
      .then(async response => {
        if (!response.ok) throw new Error("model list unavailable");
        const data = await response.json();
        if (cancelled) return;
        setModels(Array.isArray(data.models) ? data.models : []);
        setSuggestModel(String(data.default_model || ""));
        setDefaultModel(String(data.default_model || ""));
      }).catch(() => { if (!cancelled) { setModels([]); setSuggestModel(""); } })
      .finally(() => { if (!cancelled) setModelsLoaded(true); });
    return () => { cancelled = true; };
  }, [apiUrl, headers]);

  const saveDefaultModel = async (model: string | null) => {
    setModelMessage("");
    try {
      const response = await fetchWithTimeout(`${apiUrl}/feed_items/content_group_model`, {
        method: "PUT", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify({ model }),
      }, ACTION_TIMEOUT_MS);
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Nie udało się zapisać modelu");
      setDefaultModel(String(data.default_model || ""));
      if (model === null) setSuggestModel(String(data.default_model || ""));
      setModelMessage(model === null ? "Przywrócono model domyślny serwera." : "Zapisano jako domyślny model podpowiedzi tematów.");
    } catch (cause) { setError(describeActionError(cause, apiUrl, "Nie udało się zapisać modelu")); }
  };

  const load = React.useCallback(async function loadPage(nextPage = pageRef.current, landing?: "first" | "last") {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ status, limit: String(pageSize), offset: String((nextPage - 1) * pageSize) });
      if (selectedSource) params.set("feed_source_id", selectedSource);
      const [itemsResponse, sourcesResponse, groupsResponse] = await Promise.all([
        fetch(`${apiUrl}/feed_items?${params.toString()}`, { headers }),
        fetch(`${apiUrl}/feed_sources`, { headers }),
        fetch(`${apiUrl}/content_groups`, { headers }),
      ]);
      const readResponse = async (response: Response): Promise<Record<string, unknown>> => {
        const text = await response.text();
        if (!text) return {};
        try { return JSON.parse(text) as Record<string, unknown>; } catch { return { message: text }; }
      };
      const itemsData = await readResponse(itemsResponse);
      const sourcesData = await readResponse(sourcesResponse);
      const groupsData = await readResponse(groupsResponse);
      if (!itemsResponse.ok) {
        const detail = itemsResponse.status === 401 || itemsResponse.status === 403
          ? "Klucz API nie ma uprawnień użytkownika do kuracji feedów"
          : String(itemsData.message || "Nie udało się pobrać wpisów feedu");
        throw new Error(`${detail} (HTTP ${itemsResponse.status}, ${apiUrl}/feed_items)`);
      }
      if (!sourcesResponse.ok) {
        const detail = sourcesResponse.status === 401 || sourcesResponse.status === 403
          ? "Klucz API nie ma uprawnień użytkownika do źródeł feedów"
          : String(sourcesData.message || "Nie udało się pobrać źródeł");
        throw new Error(`${detail} (HTTP ${sourcesResponse.status}, ${apiUrl}/feed_sources)`);
      }
      const nextItems = Array.isArray(itemsData.feed_items) ? itemsData.feed_items as FeedItem[] : [];
      const lastPage = Math.max(1, Math.ceil(Number(itemsData.total ?? 0) / pageSize));
      if (nextPage > lastPage) { await loadPage(lastPage, "last"); return; }
      setItems(nextItems);
      setIndex(current => landing === "first" ? 0 : landing === "last" ? Math.max(0, nextItems.length - 1) : Math.min(current, Math.max(0, nextItems.length - 1)));
      pageRef.current = nextPage;
      setTotal(Number(itemsData.total ?? 0));
      setPage(nextPage);
      setSources(Array.isArray(sourcesData.feed_sources) ? sourcesData.feed_sources as FeedSource[] : []);
      setContentGroups(Array.isArray(groupsData.content_groups) ? groupsData.content_groups as ContentGroup[] : []);
    } catch (cause) {
      setError(cause instanceof TypeError
        ? `Nie można połączyć się z API ${apiUrl}. Sprawdź adres API, CORS i połączenie z NAS-em.`
        : cause instanceof Error ? cause.message : "Nie udało się pobrać feedu");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, headers, selectedSource, status]);

  React.useEffect(() => { void load(); }, [load]);

  // Open the item named in the address once the first page has loaded: in the list, else fetched on its own.
  React.useEffect(() => {
    if (itemResolved || loading) return;
    const id = Number(initialItemRef.current);
    const position = items.findIndex(item => item.id === id);
    if (position >= 0) { setIndex(position); setItemResolved(true); return; }
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetchWithTimeout(`${apiUrl}/feed_items/${id}`, { headers }, ACTION_TIMEOUT_MS);
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.message || `Nie znaleziono wpisu #${id} (${response.status})`);
        if (!cancelled) setPinned((data.feed_item ?? data) as FeedItem);
      } catch (cause) {
        if (!cancelled) setError(describeActionError(cause, apiUrl, "Nie udało się otworzyć wpisu z linku"));
      } finally { if (!cancelled) setItemResolved(true); }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, headers, items, itemResolved, loading]);

  const displayedItem: FeedItem | undefined = mode === "single" && !loading ? pinned ?? items[index] : undefined;

  // Keep the address on the displayed item so the browser URL is always the link to copy.
  React.useEffect(() => {
    if (!itemResolved) return;
    const current = searchParams.get("item");
    const wanted = mode === "single" && displayedItem ? String(displayedItem.id) : null;
    if (current === wanted || (mode === "single" && !displayedItem)) return;
    const next = new URLSearchParams(searchParams);
    if (wanted) next.set("item", wanted); else next.delete("item");
    setSearchParams(next, { replace: true });
  }, [displayedItem, itemResolved, mode, searchParams, setSearchParams]);

  const shareUrl = displayedItem
    ? `${window.location.origin}${window.location.pathname}?${new URLSearchParams({ item: String(displayedItem.id), ...(displayedItem.status === "saved_for_later" ? { view: "later" } : {}) }).toString()}`
    : "";
  const copyShareUrl = async () => {
    try { await navigator.clipboard.writeText(shareUrl); setLinkMessage("Skopiowano link."); }
    catch { setLinkMessage("Nie udało się skopiować — zaznacz link i skopiuj ręcznie."); }
  };

  const loadHistory = React.useCallback(async () => {
    setHistoryLoading(true);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (selectedSource) params.set("feed_source_id", selectedSource);
      const response = await fetchWithTimeout(`${apiUrl}/feed_review_decisions?${params.toString()}`, { headers }, ACTION_TIMEOUT_MS);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || `Nie udało się pobrać historii (${response.status})`);
      setDecisions(Array.isArray(data.decisions) ? data.decisions as ReviewDecision[] : []);
    } catch (cause) {
      setError(describeActionError(cause, apiUrl, "Nie udało się pobrać historii"));
    } finally { setHistoryLoading(false); }
  }, [apiUrl, headers, selectedSource]);

  React.useEffect(() => { if (showHistory) void loadHistory(); }, [loadHistory, showHistory]);

  const updateParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    const nextSource = Object.prototype.hasOwnProperty.call(changes, "feed_source_id")
      ? changes.feed_source_id || ""
      : selectedSource;
    const nextView = Object.prototype.hasOwnProperty.call(changes, "view")
      ? changes.view === "later" ? "later" : "new"
      : view;
    saveFeedReviewFilters({ feedSourceId: nextSource, view: nextView, mode: changes.mode === undefined ? mode : changes.mode === "all" ? "all" : "single" });
    if (Object.keys(changes).every(key => key === "mode")) { setSearchParams(next); return; }
    next.delete("item");
    setPinned(null);
    pageRef.current = 1;
    setIndex(0);
    setPage(1);
    setSearchParams(next);
  };

  const act = async (id: number, action: Action, body?: object) => {
    setBusyItemId(id);
    setError("");
    setItemError(null);
    try {
      const response = await fetchWithTimeout(`${apiUrl}/feed_items/${id}/${action}`, {
        method: "POST", headers: { ...headers, "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      }, action === "import" ? IMPORT_TIMEOUT_MS : ACTION_TIMEOUT_MS);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || data.error || `Akcja nie powiodła się (${response.status})`);
      setIgnoreItemId(null);
      setIgnorePattern("");
      setSkipItemId(null);
      setRadarItemId(null);
      setPinned(current => current?.id === id ? null : current);
      if (action === "to_radar") {
        const related = Array.isArray(data.proposed_relations) ? data.proposed_relations as string[] : [];
        const name = data.recommendation?.name ?? data.existing_tool?.name ?? "narzędzie";
        setRadarMessage(data.existing_tool ? `„${name}” jest już w Spisie narzędzi — wpis usunięto z kolejki.`
          : `${data.created ? "Dodano do radaru" : "Dopisano wzmiankę do wpisu w radarze"}: ${name}.${related.length ? ` Zaproponowane powiązania: ${related.join(", ")}.` : ""}`);
        await load();
      } else if (action === "import") {
        const requestedType = body && "document_type" in body
          ? String((body as { document_type?: string }).document_type) : "link";
        // Trust the server's resolved type: "webpage" requested on a URL already
        // stored as a bare link falls back to "link" when the page is paywalled.
        const documentType = String(data.document_type ?? requestedType);
        setImportedTypes(current => ({ ...current, [id]: documentType }));
        if (mode === "all") setItems(current => current.map(item => item.id === id ? { ...item, ...data.feed_item } : item));
        else await load();
        if (requestedType === "webpage" && documentType === "link") {
          setError("Zaimportowano jako link — nie można pobrać treści (paywall lub wymagane logowanie).");
        }
      } else if (mode === "all" && action === "save-for-later" && view === "new") {
        setItems(current => current.map(item => item.id === id ? { ...item, ...data, status: "saved_for_later" } : item));
      } else {
        await load();
      }
    } catch (cause) {
      const message = describeActionError(cause, apiUrl, "Akcja nie powiodła się");
      setError(message);
      // The page-level alert sits above the list and is easy to miss when
      // scrolled down — repeat it on the item the user just clicked.
      setItemError({ id, message });
    } finally {
      setBusyItemId(null);
    }
  };

  const sourceName = (id: number) => sources.find(source => source.id === id)?.name || `Źródło #${id}`;
  const sourceType = (id: number) => sources.find(source => source.id === id)?.type;
  const isVideo = (item: FeedItem) => sourceType(item.feed_source_id) === "youtube_channel"
    || /(?:youtube\.com\/watch\?|youtu\.be\/|youtube\.com\/shorts\/)/i.test(item.url);
  const materialLabel = (item: FeedItem) => isVideo(item) ? "Do obejrzenia" : "Do przeczytania";
  const maybeLaterGroup = contentGroups.find(group => group.kind === "priority" && group.priority_rank === 100);
  const formatDate = (value: string | null) => value ? new Date(value).toLocaleString("pl-PL") : null;

  // A plain click switches to single-item mode in place (the ?item= address is only read at mount);
  // ctrl/middle-click keeps the link's own behaviour, so it opens in a new tab.
  const openSingle = (event: React.MouseEvent, item: FeedItem) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const position = items.findIndex(candidate => candidate.id === item.id);
    setPinned(null);
    setIndex(Math.max(0, position));
    updateParams({ mode: "single" });
  };

  const renderItem = (item: FeedItem) => {
      const busy = busyItemId === item.id;
      const importedType = importedTypes[item.id];
      return <article key={item.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
        <div style={{ color: "#64748b", fontSize: ".85rem", marginBottom: 6 }}>{sourceName(item.feed_source_id)}</div>
        <h3>{item.title}</h3>
        {mode === "all" && <div style={{ marginBottom: 6 }}>
          <Link to={{ search: `?${new URLSearchParams({ mode: "single", item: String(item.id), ...(view === "later" ? { view: "later" } : {}) }).toString()}` }}
            onClick={event => openSingle(event, item)}>🔗 Pracuj nad tym wpisem</Link>
        </div>}
        {item.published_at && <div>Opublikowano: {formatDate(item.published_at)}</div>}
        {view === "later" && item.saved_at && <div>Zapisano: {formatDate(item.saved_at)}</div>}
        <a href={item.url} target="_blank" rel="noreferrer">{view === "later" ? "Otwórz materiał" : item.url}</a>
        {item.summary && <p>{item.summary}</p>}
        {modelsLoaded && <ContentGroupsPanel key={item.id} feedItemId={item.id} initialGroups={item.groups} autoSuggest={modelsLoaded} suggestModel={suggestModel || undefined} onModelCall={onModelCall} />}
        <div>
          {importedType ? <span style={{ color: "#166534", fontWeight: 600 }}>Zaimportowano jako {importedType === "youtube" ? "film" : importedType}</span> : item.status === "saved_for_later" ? <>
            <span style={{ color: "#166534", fontWeight: 600 }}>Zachowano tylko link do oceny</span>{" "}
            <button disabled={busy} onClick={() => void act(item.id, "restore")}>Przywróć do nowych</button>
          </> : view === "new" ? <>
            <button className="button" disabled={busy || item.status === "saved_for_later"} onClick={() => void act(item.id, "save-for-later")}>
              {item.status === "saved_for_later" ? "Zapisano" : materialLabel(item)}
            </button>{" "}
            {maybeLaterGroup && <button disabled={busy || item.status === "saved_for_later"} onClick={() => void act(item.id, "save-for-later", { group_ids: [maybeLaterGroup.id] })}>
              Może kiedyś
            </button>}{" "}
            {isVideo(item) ? <><button disabled={busy} onClick={() => void act(item.id, "import", { document_type: "youtube" })}>Zaimportuj jako film</button>{" "}
              <button className="button" disabled={busy} onClick={() => void act(item.id, "import", { document_type: "link" })}>Zaimportuj jako link (bez filmu)</button></> : <>
              <button disabled={busy} onClick={() => void act(item.id, "save-for-later")}>Zachowaj tylko link do oceny</button>{" "}
              <button className="button" disabled={busy} onClick={() => void act(item.id, "import", { document_type: "link", keep_for_review: true })}>Zaimportuj jako link i zapisz do przeczytania</button>{" "}
              <button disabled={busy} onClick={() => void act(item.id, "import", { document_type: "webpage" })}>Zaimportuj jako webpage</button>
            </>}{" "}
            <HelpBadge text={RADAR_HELP} />
            <button disabled={busy} onClick={() => { setRadarItemId(item.id); setRadarName(suggestToolName(item.title)); setRadarCategory(""); }}>Do radaru</button>{" "}
            <HelpBadge text={SKIP_HELP} />
            <button disabled={busy} onClick={() => { setSkipItemId(item.id); setSkipReason("not_interested"); }}>Pomiń</button>{" "}
            <HelpBadge text={IGNORE_HELP} />
            <button disabled={busy} onClick={() => { setIgnoreItemId(item.id); setIgnorePattern(""); }}>Ignoruj</button>
          </> : <>
            {isVideo(item) ? <><button className="button" disabled={busy} onClick={() => void act(item.id, "import", { document_type: "youtube" })}>Zaimportuj jako film</button>{" "}
              <button disabled={busy} onClick={() => void act(item.id, "import", { document_type: "link" })}>Zaimportuj jako link (bez filmu)</button></> : <>
              <button className="button" disabled={busy} onClick={() => void act(item.id, "import", { document_type: "link" })}>Zaimportuj jako link</button>{" "}
              <button disabled={busy} onClick={() => void act(item.id, "import", { document_type: "webpage" })}>Zaimportuj jako webpage</button>
            </>}{" "}
            <HelpBadge text={RADAR_HELP} />
            <button disabled={busy} onClick={() => { setRadarItemId(item.id); setRadarName(suggestToolName(item.title)); setRadarCategory(""); }}>Do radaru</button>{" "}
            <HelpBadge text="Nie dodawaj: odrzuca tylko ten jeden wpis, bez reguły dla źródła." />
            <button disabled={busy} onClick={() => void act(item.id, "skip")}>Nie dodawaj</button>{" "}
            <HelpBadge text={IGNORE_HELP} />
            <button disabled={busy} onClick={() => { setIgnoreItemId(item.id); setIgnorePattern(""); }}>Ignoruj</button>{" "}
            <button disabled={busy} onClick={() => void act(item.id, "restore")}>Wróć do nowych</button>
          </>}
        </div>
        {busy && <div style={{ color: "#64748b", fontSize: ".85rem", marginTop: 6 }}>Zapisywanie…</div>}
        {itemError?.id === item.id && <p className="errorText" role="alert" style={{ marginTop: 6 }}>{itemError.message}</p>}
        {ignoreItemId === item.id && <form onSubmit={event => { event.preventDefault(); void act(item.id, "ignore", { field: ignoreField, pattern: ignorePattern }); }}>
          <select aria-label="Pole wzorca" value={ignoreField} onChange={event => setIgnoreField(event.target.value as "title" | "url")} disabled={busy}>
            <option value="title">Tytuł</option><option value="url">URL</option>
          </select>{" "}
          <input aria-label="Wzorzec" value={ignorePattern} onChange={event => setIgnorePattern(event.target.value)} required disabled={busy} />{" "}
          <button type="submit" disabled={busy || !ignorePattern}>Zastosuj</button>{" "}
          <button type="button" onClick={() => setIgnoreItemId(null)} disabled={busy}>Anuluj</button>
        </form>}
        {radarItemId === item.id && <form onSubmit={event => { event.preventDefault(); void act(item.id, "to_radar", { name: radarName, category: radarCategory }); }}>
          <label>Nazwa narzędzia:{" "}
            <input aria-label="Nazwa narzędzia" value={radarName} onChange={event => setRadarName(event.target.value)} required disabled={busy} />
          </label>{" "}
          <label>Kategoria:{" "}
            <input aria-label="Kategoria narzędzia" list="radar-category-hints" value={radarCategory} onChange={event => setRadarCategory(event.target.value)} disabled={busy} placeholder="np. DecisionModels" />
          </label>
          <datalist id="radar-category-hints">{RADAR_CATEGORY_HINTS.map(value => <option key={value} value={value} />)}</datalist>{" "}
          <button type="submit" disabled={busy || !radarName.trim()}>Dodaj do radaru</button>{" "}
          <button type="button" onClick={() => setRadarItemId(null)} disabled={busy}>Anuluj</button>
        </form>}
        {skipItemId === item.id && <form onSubmit={event => { event.preventDefault(); void act(item.id, "skip", { reason: skipReason }); }}>
          <label>Powód pominięcia:{" "}
            <select aria-label="Powód pominięcia" value={skipReason} onChange={event => setSkipReason(event.target.value as ReviewReason)} disabled={busy}>
              {reviewReasons.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>{" "}
          <button type="submit" disabled={busy}>Zapisz decyzję</button>{" "}
          <button type="button" onClick={() => setSkipItemId(null)} disabled={busy}>Anuluj</button>
        </form>}
      </article>;
  };

  const pagination = <Pagination page={page} pageSize={pageSize} total={total} isLoading={loading} label="wpisów feedu" onPageChange={nextPage => { void load(nextPage); }} />;

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <h1 style={{ color: "#0c2f4a" }}>Kuracja feedów</h1>
      <button className="button" type="button" onClick={() => void load()} disabled={loading}>Odśwież</button>
    </div>
    <div role="tablist" aria-label="Widok feedu" style={{ display: "flex", gap: 8, margin: "8px 0 16px" }}>
      <button role="tab" aria-selected={view === "new"} className={view === "new" ? "button" : ""} onClick={() => updateParams({ view: null })}>Nowe</button>
      <button role="tab" aria-selected={view === "later"} className={view === "later" ? "button" : ""} onClick={() => updateParams({ view: "later" })}>Do przeczytania / obejrzenia</button>
      <button type="button" className={showHistory ? "button" : ""} onClick={() => setShowHistory(value => !value)}>Historia decyzji</button>
    </div>
    <div role="group" aria-label="Tryb przeglądu">
      <button aria-pressed={mode === "single"} onClick={() => updateParams({ mode: "single" })}>Po jednym wpisie</button>{" "}
      <button aria-pressed={mode === "all"} onClick={() => updateParams({ mode: "all" })}>Wszystkie na liście</button>
    </div>
    {showHistory && <div style={{ border: "1px solid #cbd5e1", borderRadius: 10, padding: 14, marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>Historia decyzji</h2>
        <button type="button" onClick={() => void loadHistory()} disabled={historyLoading}>Odśwież historię</button>
      </div>
      {!historyLoading && !decisions.length && <p>Brak zapisanych decyzji dla tego źródła.</p>}
      {decisions.map(decision => <div key={decision.id} style={{ borderTop: "1px solid #e2e8f0", padding: "10px 0", marginTop: 10 }}>
        <strong>{decision.title}</strong><br />
        <small>{decision.action}: {decision.previous_status} → {decision.new_status} · {formatDate(decision.created_at)} · batch {decision.batch_id}</small>{" "}
        <button type="button" onClick={async () => {
          setError("");
          try {
            const response = await fetchWithTimeout(`${apiUrl}/feed_review_decisions/${decision.id}/undo`, { method: "POST", headers }, ACTION_TIMEOUT_MS);
            const data = await response.json().catch(() => ({}));
            if (!response.ok) { setError(data.message || `Nie udało się cofnąć decyzji (${response.status})`); return; }
          } catch (cause) {
            setError(describeActionError(cause, apiUrl, "Nie udało się cofnąć decyzji"));
            return;
          }
          await loadHistory(); await load();
        }}>Cofnij</button>
      </div>)}
    </div>}
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "8px 0 20px" }}>
      Źródło:
      <select value={selectedSource} onChange={event => updateParams({ feed_source_id: event.target.value || null })} disabled={loading && sources.length === 0}>
        <option value="">Wszystkie źródła</option>
        {sources.map(source => <option key={source.id} value={source.id}>{source.name}{source.disabled ? " (wyłączony)" : ""}</option>)}
      </select>
    </label>
    {/* Fixed to the viewport, not the top of the page: the user clicks pagination
        and actions far below the header, where an inline message goes unseen. */}
    {error && <div role="alert" style={{
      position: "fixed", left: "50%", bottom: 24, transform: "translateX(-50%)", zIndex: 1000,
      maxWidth: "min(720px, calc(100vw - 32px))", display: "flex", alignItems: "flex-start", gap: 12,
      background: "#fef2f2", color: "#991b1b", border: "1px solid #fca5a5", borderRadius: 10,
      padding: "12px 16px", boxShadow: "0 6px 24px rgba(0,0,0,.2)",
    }}>
      <span style={{ flex: 1 }}>{error}</span>
      <button type="button" aria-label="Zamknij komunikat" onClick={() => setError("")}>✕</button>
    </div>}
    {radarMessage && <p role="status" style={{ color: "#166534" }}>{radarMessage} <a href="/tool-recommendations">Otwórz radar</a></p>}

    {!loading && !error && !items.length && <p>{view === "later" ? "Lista jest pusta." : "Brak nowych wpisów dla wybranego źródła."}</p>}
    {models.length > 0 && <details style={{ margin: "0 0 18px", color: "#475569" }}>
      <summary style={{ cursor: "help" }}>Model do podpowiadania tematów: <strong>{models.find(option => option.id === suggestModel)?.label ?? suggestModel}</strong></summary>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 8 }}>
        <select value={suggestModel} onChange={event => setSuggestModel(event.target.value)} aria-label="Model do podpowiadania tematów">
          {models.map(option => <option key={option.id} value={option.id}>{modelOptionText(option)}{option.id === defaultModel ? " — domyślny" : ""}</option>)}
        </select>
        <button type="button" disabled={!suggestModel || suggestModel === defaultModel} onClick={() => void saveDefaultModel(suggestModel)}>Zapisz jako domyślny</button>
        <button type="button" onClick={() => void saveDefaultModel(null)}>Przywróć domyślny serwera</button>
        {models.find(option => option.id === suggestModel)?.external && <span role="note" style={{ color: "#92400e" }}>⚠ Tytuł i podsumowanie wpisu trafią do zewnętrznego dostawcy.</span>}
        {modelMessage && <span role="status" style={{ color: "#166534" }}>{modelMessage}</span>}
      </div>
      <OpenRouterBalance refreshKey={modelCalls} />
    </details>}
    {mode === "all" && pagination}
    {displayedItem && <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", margin: "0 0 12px" }}>
      <label htmlFor="feed-item-link">Link do tego wpisu:</label>
      <input id="feed-item-link" readOnly value={shareUrl} onFocus={event => event.currentTarget.select()} style={{ flex: "1 1 360px", minWidth: 0 }} />
      <button type="button" onClick={() => void copyShareUrl()}>Kopiuj link</button>
      {linkMessage && <span role="status" style={{ color: "#166534" }}>{linkMessage}</span>}
    </div>}
    {mode === "single" && pinned && <p role="note" style={{ color: "#92400e" }}>
      Wpis otwarty z linku — spoza bieżącej listy ({pinned.status === "saved_for_later" ? "do przeczytania" : pinned.status}).{" "}
      <button type="button" onClick={() => { setPinned(null); setLinkMessage(""); }}>Wróć do listy</button>
    </p>}
    {mode === "single" && !pinned && items.length > 0 && <nav aria-label="Nawigacja wpisów" style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
      <button disabled={loading || busyItemId !== null || (page === 1 && index === 0)} onClick={() => {
        setLinkMessage("");
        if (index > 0) setIndex(index - 1); else void load(page - 1, "last");
      }}>← Poprzedni</button>
      <span>Wpis {(page - 1) * pageSize + index + 1} z {total}</span>
      <button disabled={loading || busyItemId !== null || (page - 1) * pageSize + index + 1 >= total} onClick={() => {
        setLinkMessage("");
        if (index + 1 < items.length) setIndex(index + 1); else void load(page + 1, "first");
      }}>Następny →</button>
    </nav>}
    {mode === "all" ? items.map(renderItem) : displayedItem ? renderItem(displayedItem) : null}
    {mode === "all" && pagination}

  </section>;
}
