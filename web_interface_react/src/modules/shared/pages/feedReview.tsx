import React from "react";
import { useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

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
};

type Action = "import" | "skip" | "ignore" | "save-for-later" | "restore";
type ReviewReason = "not_interested" | "duplicate" | "already_known" | "too_long" | "other";
const reviewReasons: Array<[ReviewReason, string]> = [
  ["not_interested", "Nie interesuje mnie temat"],
  ["duplicate", "Duplikat / już widziałem"],
  ["already_known", "Już to znam"],
  ["too_long", "Za długie"],
  ["other", "Inny powód"],
];

export default function FeedReview() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = React.useState<FeedItem[]>([]);
  const [sources, setSources] = React.useState<FeedSource[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busyItemId, setBusyItemId] = React.useState<number | null>(null);
  const [error, setError] = React.useState("");
  const [ignoreItemId, setIgnoreItemId] = React.useState<number | null>(null);
  const [ignoreField, setIgnoreField] = React.useState<"title" | "url">("title");
  const [ignorePattern, setIgnorePattern] = React.useState("");
  const [skipItemId, setSkipItemId] = React.useState<number | null>(null);
  const [skipReason, setSkipReason] = React.useState<ReviewReason>("not_interested");

  const selectedSource = searchParams.get("feed_source_id") || "";
  const view = searchParams.get("view") === "later" ? "later" : "new";
  const status = view === "later" ? "saved_for_later" : "new";
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "" }), [apiKey]);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ status });
      if (selectedSource) params.set("feed_source_id", selectedSource);
      const [itemsResponse, sourcesResponse] = await Promise.all([
        fetch(`${apiUrl}/feed_items?${params.toString()}`, { headers }),
        fetch(`${apiUrl}/feed_sources`, { headers }),
      ]);
      const readResponse = async (response: Response): Promise<Record<string, unknown>> => {
        const text = await response.text();
        if (!text) return {};
        try { return JSON.parse(text) as Record<string, unknown>; } catch { return { message: text }; }
      };
      const itemsData = await readResponse(itemsResponse);
      const sourcesData = await readResponse(sourcesResponse);
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
      setItems(Array.isArray(itemsData.feed_items) ? itemsData.feed_items as FeedItem[] : []);
      setSources(Array.isArray(sourcesData.feed_sources) ? sourcesData.feed_sources as FeedSource[] : []);
    } catch (cause) {
      setError(cause instanceof TypeError
        ? `Nie można połączyć się z API ${apiUrl}. Sprawdź adres API, CORS i połączenie z NAS-em.`
        : cause instanceof Error ? cause.message : "Nie udało się pobrać feedu");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, headers, selectedSource, status]);

  React.useEffect(() => { void load(); }, [load]);

  const updateParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(changes).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    setSearchParams(next);
  };

  const act = async (id: number, action: Action, body?: object) => {
    setBusyItemId(id);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/feed_items/${id}/${action}`, {
        method: "POST", headers: { ...headers, "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || data.error || `Akcja nie powiodła się (${response.status})`);
      setIgnoreItemId(null);
      setIgnorePattern("");
      setSkipItemId(null);
      if (action === "save-for-later" && view === "new") {
        setItems(current => current.map(item => item.id === id ? { ...item, ...data, status: "saved_for_later" } : item));
      } else {
        await load();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Akcja nie powiodła się");
    } finally {
      setBusyItemId(null);
    }
  };

  const sourceName = (id: number) => sources.find(source => source.id === id)?.name || `Źródło #${id}`;
  const sourceType = (id: number) => sources.find(source => source.id === id)?.type;
  const isVideo = (item: FeedItem) => sourceType(item.feed_source_id) === "youtube_channel"
    || /(?:youtube\.com\/watch\?|youtu\.be\/|youtube\.com\/shorts\/)/i.test(item.url);
  const materialLabel = (item: FeedItem) => isVideo(item) ? "Do obejrzenia" : "Do przeczytania";
  const formatDate = (value: string | null) => value ? new Date(value).toLocaleString("pl-PL") : null;

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <h1 style={{ color: "#0c2f4a" }}>Kuracja feedów</h1>
      <button className="button" type="button" onClick={() => void load()} disabled={loading}>Odśwież</button>
    </div>
    <div role="tablist" aria-label="Widok feedu" style={{ display: "flex", gap: 8, margin: "8px 0 16px" }}>
      <button role="tab" aria-selected={view === "new"} className={view === "new" ? "button" : ""} onClick={() => updateParams({ view: null })}>Nowe</button>
      <button role="tab" aria-selected={view === "later"} className={view === "later" ? "button" : ""} onClick={() => updateParams({ view: "later" })}>Do przeczytania / obejrzenia</button>
    </div>
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "8px 0 20px" }}>
      Źródło:
      <select value={selectedSource} onChange={event => updateParams({ feed_source_id: event.target.value || null })} disabled={loading && sources.length === 0}>
        <option value="">Wszystkie źródła</option>
        {sources.map(source => <option key={source.id} value={source.id}>{source.name}{source.disabled ? " (wyłączony)" : ""}</option>)}
      </select>
    </label>
    {error && <p className="errorText" role="alert">{error}</p>}
    {!loading && !error && !items.length && <p>{view === "later" ? "Lista jest pusta." : "Brak nowych wpisów dla wybranego źródła."}</p>}
    {items.map(item => {
      const busy = busyItemId === item.id;
      return <article key={item.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
        <div style={{ color: "#64748b", fontSize: ".85rem", marginBottom: 6 }}>{sourceName(item.feed_source_id)}</div>
        <h3>{item.title}</h3>
        {item.published_at && <div>Opublikowano: {formatDate(item.published_at)}</div>}
        {view === "later" && item.saved_at && <div>Zapisano: {formatDate(item.saved_at)}</div>}
        <a href={item.url} target="_blank" rel="noreferrer">{view === "later" ? "Otwórz materiał" : item.url}</a>
        {item.summary && <p>{item.summary}</p>}
        <div>
          {view === "new" ? <>
            <button className="button" disabled={busy || item.status === "saved_for_later"} onClick={() => void act(item.id, "save-for-later")}>
              {item.status === "saved_for_later" ? "Zapisano" : materialLabel(item)}
            </button>{" "}
            <button disabled={busy} onClick={() => void act(item.id, "import")}>Importuj od razu</button>{" "}
            <button disabled={busy} onClick={() => { setSkipItemId(item.id); setSkipReason("not_interested"); }}>Pomiń</button>{" "}
            <button disabled={busy} onClick={() => { setIgnoreItemId(item.id); setIgnorePattern(""); }}>Ignoruj</button>
          </> : <>
            <button className="button" disabled={busy} onClick={() => void act(item.id, "import")}>Dodaj do Lenie</button>{" "}
            <button disabled={busy} onClick={() => void act(item.id, "skip")}>Nie dodawaj</button>{" "}
            <button disabled={busy} onClick={() => void act(item.id, "restore")}>Wróć do nowych</button>
          </>}
        </div>
        {ignoreItemId === item.id && <form onSubmit={event => { event.preventDefault(); void act(item.id, "ignore", { field: ignoreField, pattern: ignorePattern }); }}>
          <select aria-label="Pole wzorca" value={ignoreField} onChange={event => setIgnoreField(event.target.value as "title" | "url")} disabled={busy}>
            <option value="title">Tytuł</option><option value="url">URL</option>
          </select>{" "}
          <input aria-label="Wzorzec" value={ignorePattern} onChange={event => setIgnorePattern(event.target.value)} required disabled={busy} />{" "}
          <button type="submit" disabled={busy || !ignorePattern}>Zastosuj</button>{" "}
          <button type="button" onClick={() => setIgnoreItemId(null)} disabled={busy}>Anuluj</button>
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
    })}
  </section>;
}
