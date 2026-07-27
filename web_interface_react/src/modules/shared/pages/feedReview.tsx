import React from "react";
import { useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

type FeedSource = { id: number; name: string; disabled: boolean };
type FeedItem = {
  id: number;
  feed_source_id: number;
  title: string;
  url: string;
  summary: string | null;
};

export default function FeedReview() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = React.useState<FeedItem[]>([]);
  const [sources, setSources] = React.useState<FeedSource[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const selectedSource = searchParams.get("feed_source_id") || "";
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "" }), [apiKey]);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ status: "new" });
      if (selectedSource) params.set("feed_source_id", selectedSource);
      const [itemsResponse, sourcesResponse] = await Promise.all([
        fetch(`${apiUrl}/feed_items?${params.toString()}`, { headers }),
        fetch(`${apiUrl}/feed_sources`, { headers }),
      ]);
      const itemsData = await itemsResponse.json();
      const sourcesData = await sourcesResponse.json();
      if (!itemsResponse.ok) throw new Error(itemsData.message || "Nie udało się pobrać wpisów feedu");
      if (!sourcesResponse.ok) throw new Error(sourcesData.message || "Nie udało się pobrać źródeł");
      setItems(itemsData.feed_items || []);
      setSources(sourcesData.feed_sources || []);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Nie udało się pobrać feedu");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, headers, selectedSource]);

  React.useEffect(() => { void load(); }, [load]);

  const changeSource = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const value = event.target.value;
    if (value) setSearchParams({ feed_source_id: value });
    else setSearchParams({});
  };

  const sourceName = (id: number) => sources.find(source => source.id === id)?.name || `Źródło #${id}`;

  const act = async (id: number, action: "import" | "skip" | "ignore") => {
    await fetch(`${apiUrl}/feed_items/${id}/${action}`, { method: "POST", headers });
    void load();
  };

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <h1 style={{ color: "#0c2f4a" }}>Kuracja feedów</h1>
      <button className="button" type="button" onClick={() => void load()} disabled={loading}>Odśwież</button>
    </div>
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "8px 0 20px" }}>
      Źródło:
      <select value={selectedSource} onChange={changeSource} disabled={loading && sources.length === 0}>
        <option value="">Wszystkie źródła</option>
        {sources.map(source => <option key={source.id} value={source.id}>{source.name}{source.disabled ? " (wyłączony)" : ""}</option>)}
      </select>
    </label>
    {error && <p className="errorText">{error}</p>}
    {!loading && !error && !items.length && <p>Brak nowych wpisów dla wybranego źródła.</p>}
    {items.map(item => <article key={item.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
      <div style={{ color: "#64748b", fontSize: ".85rem", marginBottom: 6 }}>{sourceName(item.feed_source_id)}</div>
      <h3>{item.title}</h3>
      <a href={item.url} target="_blank" rel="noreferrer">{item.url}</a>
      {item.summary && <p>{item.summary}</p>}
      <button className="button" onClick={() => void act(item.id, "import")}>Importuj</button>{" "}
      <button onClick={() => void act(item.id, "skip")}>Pomiń</button>{" "}
      <button onClick={() => void act(item.id, "ignore")}>Ignoruj</button>
    </article>)}
  </section>;
}
