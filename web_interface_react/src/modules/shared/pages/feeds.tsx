import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";
import type { ContentGroup } from "../../../types";

type Feed = {
  id: number;
  name: string;
  type: string;
  url: string | null;
  channel_id: string | null;
  author_name: string | null;
  language: string;
  tags: string[];
  default_topic_group_ids: number[];
  auto_import: boolean;
  auto_import_after: string | null;
  disabled: boolean;
  default_state: string;
  last_checked_at: string | null;
  last_error: string | null;
};

type Form = Pick<Feed, "type" | "url" | "channel_id" | "author_name" | "language" | "tags" | "default_topic_group_ids" | "auto_import" | "auto_import_after" | "disabled" | "default_state">;

const emptyForm: Form = {
  type: "rss", url: "", channel_id: "", language: "pl", tags: [],
  author_name: "",
  default_topic_group_ids: [],
  auto_import: false, auto_import_after: null, disabled: false, default_state: "URL_ADDED",
};

const toLocalInput = (value: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const toIso = (value: string) => value ? new Date(value).toISOString() : null;

export default function Feeds() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [feeds, setFeeds] = React.useState<Feed[]>([]);
  const [contentGroups, setContentGroups] = React.useState<ContentGroup[]>([]);
  const [editing, setEditing] = React.useState<number | null>(null);
  const [form, setForm] = React.useState<Form>(emptyForm);
  const [busy, setBusy] = React.useState<number | null>(null);
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState(false);

  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "" }), [apiKey]);
  const readJson = async (response: Response) => {
    const raw = await response.text();
    try { return JSON.parse(raw); }
    catch { throw new Error(`API zwróciło HTML zamiast JSON (${response.status}). Sprawdź adres API: ${response.url}`); }
  };
  const load = React.useCallback(async () => {
    const [response, groupsResponse] = await Promise.all([
      fetch(`${apiUrl}/feed_sources`, { headers }),
      fetch(`${apiUrl}/content_groups`, { headers }),
    ]);
    const [data, groupsData] = await Promise.all([readJson(response), readJson(groupsResponse)]);
    if (!response.ok || !groupsResponse.ok) throw new Error(data.message || groupsData.message || "Nie udało się pobrać konfiguracji feedów");
    setFeeds(data.feed_sources || []);
    setContentGroups((groupsData.content_groups || []).filter((group: ContentGroup) => group.kind === "topic"));
  }, [apiUrl, headers]);

  React.useEffect(() => { void load().catch(e => { setError(true); setMessage(e.message); }); }, [load]);

  const startEdit = (feed: Feed) => {
    setEditing(feed.id);
    setForm({
      type: feed.type,
      url: feed.url || "",
      channel_id: feed.channel_id || "",
      author_name: feed.author_name || "",
      language: feed.language,
      tags: feed.tags || [],
      default_topic_group_ids: feed.default_topic_group_ids || [],
      auto_import: feed.auto_import,
      auto_import_after: toLocalInput(feed.auto_import_after),
      disabled: feed.disabled,
      default_state: feed.default_state,
    });
    setMessage("");
  };

  const save = async (feed: Feed) => {
    if (form.type !== "youtube_channel" && !(form.url || "").trim()) { setError(true); setMessage("URL feedu jest wymagany."); return; }
    if (form.type === "youtube_channel" && !form.channel_id?.trim()) { setError(true); setMessage("ID kanału YouTube jest wymagane."); return; }
    setBusy(feed.id); setError(false); setMessage("");
    try {
      const payload = { ...form, url: form.type === "youtube_channel" ? null : (form.url || "").trim(), channel_id: form.type === "youtube_channel" ? form.channel_id?.trim() : null, author_name: form.type === "youtube_channel" ? form.author_name?.trim() || null : null, auto_import_after: toIso(form.auto_import_after || "") };
      const response = await fetch(`${apiUrl}/feed_sources/${feed.id}`, { method: "PATCH", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.message || "Nie udało się zapisać zmian");
      setFeeds(current => current.map(item => item.id === feed.id ? data : item));
      setEditing(null); setMessage("Zapisano zmiany.");
    } catch (e) { setError(true); setMessage(e instanceof Error ? e.message : "Nie udało się zapisać zmian"); }
    finally { setBusy(null); }
  };

  const check = async (id: number) => {
    const response = await fetch(`${apiUrl}/feed_sources/${id}/check`, { method: "POST", headers });
    setError(!response.ok); setMessage(response.ok ? "Check dodany do kolejki." : "Nie udało się dodać checku.");
  };
  const update = <K extends keyof Form>(key: K, value: Form[K]) => setForm(current => ({ ...current, [key]: value }));
  const toggleTopic = (groupId: number) => update("default_topic_group_ids", form.default_topic_group_ids.includes(groupId)
    ? form.default_topic_group_ids.filter(id => id !== groupId)
    : [...form.default_topic_group_ids, groupId]);
  const inputStyle: React.CSSProperties = { width: "100%", padding: "8px 10px", border: "1px solid #cbd5e1", borderRadius: 6 };

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
      <div><h1 style={{ marginBottom: 6, color: "#0c2f4a" }}>Feedy</h1><p style={{ color: "#64748b" }}>Źródła artykułów i automatycznego importu.</p></div>
      <button className="button" type="button" onClick={() => void load()}>Odśwież</button>
    </div>
    {message && <p className={error ? "errorText" : undefined} style={error ? undefined : { color: "#2e7d43", margin: "14px 0" }}>{message}</p>}
    <div style={{ display: "grid", gap: 12, marginTop: 20 }}>
      {feeds.map(feed => editing === feed.id ? <article key={feed.id} style={{ border: "1px solid #bae6fd", borderRadius: 10, padding: 18, background: "#f8fafc" }}>
        <h2 style={{ color: "#0c2f4a", marginBottom: 14 }}>{feed.name}</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          <label>Typ<select value={form.type} onChange={e => update("type", e.target.value)} style={inputStyle}><option value="rss">RSS</option><option value="wordpress">WordPress</option><option value="json_api">JSON API</option><option value="youtube_channel">Kanał YouTube</option></select></label>
          {form.type === "youtube_channel" ? <label>ID kanału<input value={form.channel_id || ""} onChange={e => update("channel_id", e.target.value)} style={inputStyle} /></label> : <label>URL<input value={form.url || ""} onChange={e => update("url", e.target.value)} style={inputStyle} /></label>}
          {form.type === "youtube_channel" && <label>Autor / kanał<input value={form.author_name || ""} onChange={e => update("author_name", e.target.value)} style={inputStyle} /><small style={{ color: "#64748b" }}>Opcjonalna, jawna nazwa twórcy zapisywana przy imporcie.</small></label>}
          <label>Język<input value={form.language} onChange={e => update("language", e.target.value)} style={inputStyle} /></label>
          <label>Importuj od<input type="datetime-local" value={form.auto_import_after || ""} onChange={e => update("auto_import_after", e.target.value)} style={inputStyle} /><small style={{ color: "#64748b" }}>Czas lokalny przeglądarki; zapis UTC.</small></label>
        </div>
        <label style={{ display: "flex", gap: 8, marginTop: 14 }}><input type="checkbox" checked={form.auto_import} onChange={e => update("auto_import", e.target.checked)} /> Automatyczny import</label>
        <label style={{ display: "flex", gap: 8, marginTop: 8 }}><input type="checkbox" checked={form.disabled} onChange={e => update("disabled", e.target.checked)} /> Feed wyłączony</label>
        <fieldset style={{ border: 0, padding: 0, margin: "16px 0 0" }}>
          <legend style={{ fontWeight: 600 }}>Domyślne tematy dokumentów</legend>
          <small style={{ color: "#64748b" }}>Dodawane do każdego dokumentu zaimportowanego z tego feedu.</small>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 8 }}>
            {contentGroups.map(group => <label key={group.id} style={{ display: "flex", gap: 5 }}><input type="checkbox" checked={form.default_topic_group_ids.includes(group.id)} onChange={() => toggleTopic(group.id)} /> {group.name}</label>)}
            {!contentGroups.length && <span style={{ color: "#64748b" }}>Brak zdefiniowanych tematów.</span>}
          </div>
        </fieldset>
        <div style={{ display: "flex", gap: 8, marginTop: 18 }}><button className="button" type="button" disabled={busy === feed.id} onClick={() => void save(feed)}>Zapisz</button><button type="button" onClick={() => setEditing(null)}>Anuluj</button></div>
      </article> : <article key={feed.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", background: feed.disabled ? "#f8fafc" : "#fff", opacity: feed.disabled ? .72 : 1 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><strong style={{ color: "#0f4c81", fontSize: "1.05rem" }}>{feed.name}</strong><span style={{ background: feed.auto_import ? "#dcfce7" : "#f1f5f9", color: feed.auto_import ? "#166534" : "#475569", borderRadius: 999, padding: "3px 9px", fontSize: ".78rem" }}>{feed.auto_import ? "auto import" : "ręcznie"}</span>{feed.disabled && <span style={{ color: "#b45309" }}>wyłączony</span>}<span style={{ marginLeft: "auto", display: "flex", gap: 8 }}><button className="button" type="button" onClick={() => startEdit(feed)}>Edytuj</button><button type="button" onClick={() => void check(feed.id)}>Sprawdź teraz</button></span></div>
        <div style={{ color: "#64748b", fontSize: ".85rem", marginTop: 8 }}>{feed.url || feed.channel_id || "brak adresu"} · próg: {feed.auto_import_after ? new Date(feed.auto_import_after).toLocaleString("pl-PL") : "brak"}</div>
        {feed.author_name && <div style={{ color: "#475569", fontSize: ".85rem", marginTop: 6 }}>Autor / kanał: {feed.author_name}</div>}
        {!!feed.default_topic_group_ids?.length && <div style={{ color: "#475569", fontSize: ".85rem", marginTop: 6 }}>Tematy domyślne: {contentGroups.filter(group => feed.default_topic_group_ids.includes(group.id)).map(group => group.name).join(", ")}</div>}
        {feed.last_error && <div style={{ color: "#b91c1c", marginTop: 8 }}>{feed.last_error}</div>}
      </article>)}
    </div>
    {!feeds.length && <p style={{ color: "#64748b", marginTop: 20 }}>Brak feedów.</p>}
  </section>;
}
