import React from "react";
import { useSearchParams } from "react-router-dom";
import SkillHint from "../components/SkillHint";
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

const buildPayload = (form: Form) => ({ ...form, tags: [...new Set(form.tags.map(tag => tag.trim()).filter(Boolean))], url: form.type === "youtube_channel" ? null : (form.url || "").trim(), channel_id: form.type === "youtube_channel" ? form.channel_id?.trim() : null, author_name: form.type === "youtube_channel" ? form.author_name?.trim() || null : null, auto_import_after: toIso(form.auto_import_after || "") });

export default function Feeds() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const status = ["active", "disabled", "all"].includes(searchParams.get("status") || "") ? searchParams.get("status")! : "active";
  const selectedTags = searchParams.getAll("tag");
  const query = new URLSearchParams();
  if (status !== "all") query.set("disabled", status === "disabled" ? "1" : "0");
  selectedTags.forEach(tag => query.append("tag", tag));
  const queryString = query.toString();
  const [counts, setCounts] = React.useState({ active: 0, disabled: 0 });
  const [tags, setTags] = React.useState<{ tag: string; count: number }[]>([]);
  const [search, setSearch] = React.useState("");
  const [selected, setSelected] = React.useState<number[]>([]);
  const [undo, setUndo] = React.useState<{ ids: number[]; disabled: boolean; message: string } | null>(null);
  const [feeds, setFeeds] = React.useState<Feed[]>([]);
  const [contentGroups, setContentGroups] = React.useState<ContentGroup[]>([]);
  const [editing, setEditing] = React.useState<number | null>(null);
  const [adding, setAdding] = React.useState(false);
  const [newName, setNewName] = React.useState("");
  const [editName, setEditName] = React.useState("");
  const [form, setForm] = React.useState<Form>(emptyForm);
  const [tagsText, setTagsText] = React.useState("");
  const [busy, setBusy] = React.useState<number | null>(null);
  const [fetchingTitle, setFetchingTitle] = React.useState(false);
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
      fetch(`${apiUrl}/feed_sources${queryString ? `?${queryString}` : ""}`, { headers }),
      fetch(`${apiUrl}/content_groups`, { headers }),
    ]);
    const [data, groupsData] = await Promise.all([readJson(response), readJson(groupsResponse)]);
    if (!response.ok || !groupsResponse.ok) throw new Error(data.message || groupsData.message || "Nie udało się pobrać konfiguracji feedów");
    setFeeds(data.feed_sources || []);
    setCounts(data.counts || { active: 0, disabled: 0 });
    setTags(data.tags || []);
    setContentGroups((groupsData.content_groups || []).filter((group: ContentGroup) => group.kind === "topic"));
  }, [apiUrl, headers, queryString]);

  React.useEffect(() => { void load().catch(e => { setError(true); setMessage(e.message); }); }, [load]);

  React.useEffect(() => { setSelected([]); }, [queryString, search]);
  React.useEffect(() => {
    if (!undo) return;
    const timer = window.setTimeout(() => setUndo(null), 15000);
    return () => window.clearTimeout(timer);
  }, [undo]);

  const visibleFeeds = feeds.filter(feed => feed.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const visibleSelected = selected.filter(id => visibleFeeds.some(feed => feed.id === id));
  const changeFilter = (key: "status" | "tag", value: string) => {
    const next = new URLSearchParams(searchParams);
    if (key === "status") next.set(key, value);
    else {
      next.delete("tag");
      (selectedTags.includes(value) ? selectedTags.filter(tag => tag !== value) : [...selectedTags, value]).forEach(tag => next.append("tag", tag));
    }
    setSearchParams(next);
  };
  const changeDisabled = async (disabled: boolean, target: { feed_ids: number[] } | { tag: string }, single?: Feed, reverting = false) => {
    setBusy(single?.id ?? 0); setError(false); setMessage("");
    try {
      const response = await fetch(`${apiUrl}/feed_sources/${single ? single.id : "bulk-disable"}`, {
        method: single ? "PATCH" : "POST", headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(single ? { disabled } : { disabled, ...target }),
      });
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.message || "Nie udało się zmienić feedów");
      const ids: number[] = single ? [single.id] : data.feed_ids;
      setUndo(reverting ? null : { ids, disabled: !disabled, message: single ? `${disabled ? "Wyłączono" : "Włączono"}: ${single.name}` : `Zmieniono ${data.changed} feedów` });
      if (reverting) setMessage("Cofnięto zmiany.");
      setSelected([]);
      await load();
    } catch (e) { setError(true); setMessage(e instanceof Error ? e.message : "Nie udało się zmienić feedów"); }
    finally { setBusy(null); }
  };
  const changeTag = (disabled: boolean) => {
    const count = disabled ? counts.active : counts.disabled;
    if (window.confirm(`${disabled ? "Wyłączyć" : "Włączyć"} wszystkie feedy z tagiem ${selectedTags[0]} (${count})?`)) {
      void changeDisabled(disabled, { tag: selectedTags[0] });
    }
  };

  const startEdit = (feed: Feed) => {
    setAdding(false);
    setEditing(feed.id);
    setEditName(feed.name);
    setTagsText((feed.tags || []).join(", "));
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

  const validateForm = () => {
    if (form.type !== "youtube_channel" && !(form.url || "").trim()) { setError(true); setMessage("URL feedu jest wymagany."); return false; }
    if (form.type === "youtube_channel" && !form.channel_id?.trim()) { setError(true); setMessage("ID kanału YouTube jest wymagane."); return false; }
    return true;
  };

  const save = async (feed: Feed) => {
    if (!editName.trim()) { setError(true); setMessage("Nazwa feedu jest wymagana."); return; }
    if (!validateForm()) return;
    setBusy(feed.id); setError(false); setMessage("");
    try {
      const payload = { name: editName.trim(), ...buildPayload(form) };
      const response = await fetch(`${apiUrl}/feed_sources/${feed.id}`, { method: "PATCH", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.message || "Nie udało się zapisać zmian");
      await load();
      setEditing(null); setMessage("Zapisano zmiany.");
    } catch (e) { setError(true); setMessage(e instanceof Error ? e.message : "Nie udało się zapisać zmian"); }
    finally { setBusy(null); }
  };

  const add = async () => {
    if (!newName.trim()) { setError(true); setMessage("Nazwa feedu jest wymagana."); return; }
    if (!validateForm()) return;
    setBusy(0); setError(false); setMessage("");
    try {
      const response = await fetch(`${apiUrl}/feed_sources`, {
        method: "POST", headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim(), ...buildPayload(form) }),
      });
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.message || "Nie udało się dodać feedu");
      setAdding(false);
      await load();
      setMessage("Dodano feed.");
    } catch (e) { setError(true); setMessage(e instanceof Error ? e.message : "Nie udało się dodać feedu"); }
    finally { setBusy(null); }
  };

  const check = async (id: number) => {
    const response = await fetch(`${apiUrl}/feed_sources/${id}/check`, { method: "POST", headers });
    setError(!response.ok); setMessage(response.ok ? "Check dodany do kolejki." : "Nie udało się dodać checku.");
  };
  const fetchTitle = async (setName: (name: string) => void) => {
    if (!validateForm()) return;
    setFetchingTitle(true); setError(false); setMessage("");
    try {
      const response = await fetch(`${apiUrl}/feed_sources/fetch_title`, {
        method: "POST", headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ type: form.type, url: (form.url || "").trim(), channel_id: (form.channel_id || "").trim() }),
      });
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.message || "Nie udało się pobrać tytułu");
      setName(data.title);
    } catch (e) { setError(true); setMessage(e instanceof Error ? e.message : "Nie udało się pobrać tytułu"); }
    finally { setFetchingTitle(false); }
  };
  const nameField = (value: string, setName: (name: string) => void) => <div style={{ marginBottom: 12 }}>
    <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
      <label style={{ flex: 1 }}>Nazwa<input required value={value} onChange={e => setName(e.target.value)} style={inputStyle} /></label>
      <button type="button" disabled={fetchingTitle} onClick={() => void fetchTitle(setName)} style={{ whiteSpace: "nowrap" }}>{fetchingTitle ? "Pobieram…" : "Pobierz tytuł"}</button>
    </div>
    <small style={{ color: "#64748b" }}>Tytuł odczytany z samego feedu (po wpisaniu adresu lub ID kanału); możesz go potem zmienić.</small>
  </div>;
  const update = <K extends keyof Form>(key: K, value: Form[K]) => setForm(current => ({ ...current, [key]: value }));
  const toggleTopic = (groupId: number) => update("default_topic_group_ids", form.default_topic_group_ids.includes(groupId)
    ? form.default_topic_group_ids.filter(id => id !== groupId)
    : [...form.default_topic_group_ids, groupId]);
  const inputStyle: React.CSSProperties = { width: "100%", padding: "8px 10px", border: "1px solid #cbd5e1", borderRadius: 6 };

  const renderFields = () => <>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          <label>Typ<select value={form.type} onChange={e => update("type", e.target.value)} style={inputStyle}><option value="rss">RSS</option><option value="wordpress">WordPress</option><option value="json_api">JSON API</option><option value="youtube_channel">Kanał YouTube</option></select></label>
          {form.type === "youtube_channel" ? <label>ID kanału<input value={form.channel_id || ""} onChange={e => update("channel_id", e.target.value)} style={inputStyle} /></label> : <label>URL<input value={form.url || ""} onChange={e => update("url", e.target.value)} style={inputStyle} /></label>}
          {form.type === "youtube_channel" && <label>Autor / kanał<input value={form.author_name || ""} onChange={e => update("author_name", e.target.value)} style={inputStyle} /><small style={{ color: "#64748b" }}>Opcjonalna, jawna nazwa twórcy zapisywana przy imporcie.</small></label>}
          <label>Język<input value={form.language} onChange={e => update("language", e.target.value)} style={inputStyle} /></label>
          <label>Tagi (po przecinku)<input value={tagsText} onChange={e => { setTagsText(e.target.value); update("tags", e.target.value.split(",")); }} style={inputStyle} /></label>
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
  </>;

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
      <div><h1 style={{ marginBottom: 6, color: "#0c2f4a" }}>Feedy<SkillHint skill="/lenie-feed-review" command="/lenie-feed-review">Nowych kandydatów z feedów przejrzysz też w sesji z Claude'em, pojedynczo, z decyzją po Twojej stronie.</SkillHint></h1><p style={{ color: "#64748b" }}>Źródła artykułów i automatycznego importu.</p></div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="button" type="button" disabled={busy !== null} onClick={() => {
          setAdding(true); setNewName(""); setTagsText(""); setForm(emptyForm); setEditing(null); setMessage(""); setError(false);
        }}>Dodaj feed</button>
        <button className="button" type="button" onClick={() => void load()}>Odśwież</button>
      </div>
    </div>
    <div aria-label="Filtry feedów" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
      {([ ["active", "Aktywne", counts.active], ["disabled", "Wyłączone", counts.disabled], ["all", "Wszystkie", counts.active + counts.disabled] ] as const).map(([value, label, count]) => <button key={value} type="button" aria-pressed={status === value} onClick={() => changeFilter("status", value)}>{label} ({count})</button>)}
      {tags.map(({ tag, count }) => <button key={tag} type="button" aria-pressed={selectedTags.includes(tag)} onClick={() => changeFilter("tag", tag)} style={{ borderRadius: 999 }}>{tag} ({count})</button>)}
      <label>Szukaj po nazwie<input value={search} onChange={e => setSearch(e.target.value)} /></label>
    </div>
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
      <label><input type="checkbox" checked={visibleFeeds.length > 0 && visibleSelected.length === visibleFeeds.length} onChange={e => setSelected(e.target.checked ? visibleFeeds.map(feed => feed.id) : [])} /> Zaznacz wszystkie widoczne</label>
      {visibleSelected.length > 0 && <>
        <button disabled={busy !== null} onClick={() => void changeDisabled(true, { feed_ids: visibleSelected })}>Wyłącz zaznaczone ({visibleSelected.length})</button>
        <button disabled={busy !== null} onClick={() => void changeDisabled(false, { feed_ids: visibleSelected })}>Włącz zaznaczone ({visibleSelected.length})</button>
      </>}
      {selectedTags.length === 1 && <>
        <button disabled={busy !== null || counts.active === 0} onClick={() => changeTag(true)}>Wyłącz wszystkie z tagiem {selectedTags[0]} ({counts.active})</button>
        <button disabled={busy !== null || counts.disabled === 0} onClick={() => changeTag(false)}>Włącz wszystkie z tagiem {selectedTags[0]} ({counts.disabled})</button>
      </>}
    </div>
    {undo && <p role="status">{undo.message} · <button disabled={busy !== null} onClick={() => void changeDisabled(undo.disabled, { feed_ids: undo.ids }, undefined, true)}>Cofnij</button></p>}
    {message && <p className={error ? "errorText" : undefined} style={error ? undefined : { color: "#2e7d43", margin: "14px 0" }}>{message}</p>}
    <div style={{ display: "grid", gap: 12, marginTop: 20 }}>
      {adding && <article style={{ border: "1px solid #bae6fd", borderRadius: 10, padding: 18, background: "#f8fafc" }}>
        <h2 style={{ color: "#0c2f4a", marginBottom: 14 }}>Dodaj feed</h2>
        {nameField(newName, setNewName)}
        {renderFields()}
        <div style={{ display: "flex", gap: 8, marginTop: 18 }}><button className="button" type="button" disabled={busy !== null} onClick={() => void add()}>Dodaj</button><button type="button" onClick={() => setAdding(false)}>Anuluj</button></div>
      </article>}
      {visibleFeeds.map(feed => editing === feed.id ? <article key={feed.id} style={{ border: "1px solid #bae6fd", borderRadius: 10, padding: 18, background: "#f8fafc" }}>
        <h2 style={{ color: "#0c2f4a", marginBottom: 14 }}>{feed.name}</h2>
        {nameField(editName, setEditName)}
        {renderFields()}
        <div style={{ display: "flex", gap: 8, marginTop: 18 }}><button className="button" type="button" disabled={busy === feed.id} onClick={() => void save(feed)}>Zapisz</button><button type="button" onClick={() => setEditing(null)}>Anuluj</button></div>
      </article> : <article key={feed.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", background: feed.disabled ? "#f8fafc" : "#fff", opacity: feed.disabled ? .72 : 1 }}>
        <label><input type="checkbox" aria-label={`Zaznacz ${feed.name}`} checked={visibleSelected.includes(feed.id)} onChange={e => setSelected(current => e.target.checked ? [...current, feed.id] : current.filter(id => id !== feed.id))} /> Zaznacz</label>
        <button type="button" disabled={busy !== null} onClick={() => void changeDisabled(!feed.disabled, { feed_ids: [feed.id] }, feed)}>{feed.disabled ? "Wyłączony" : "Aktywny"}</button>
        <div style={{ display: "flex", gap: 6, margin: "6px 0" }}>{feed.tags?.map(tag => <span key={tag} style={{ borderRadius: 999, background: "#e2e8f0", padding: "3px 9px" }}>{tag}</span>)}</div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><strong style={{ color: "#0f4c81", fontSize: "1.05rem" }}>{feed.name}</strong><span style={{ background: feed.auto_import ? "#dcfce7" : "#f1f5f9", color: feed.auto_import ? "#166534" : "#475569", borderRadius: 999, padding: "3px 9px", fontSize: ".78rem" }}>{feed.auto_import ? "auto import" : "ręcznie"}</span>{feed.disabled && <span style={{ color: "#b45309" }}>wyłączony</span>}<span style={{ marginLeft: "auto", display: "flex", gap: 8 }}><button className="button" type="button" onClick={() => startEdit(feed)}>Edytuj</button><button type="button" onClick={() => void check(feed.id)}>Sprawdź teraz</button></span></div>
        <div style={{ color: "#64748b", fontSize: ".85rem", marginTop: 8 }}>{feed.url || feed.channel_id || "brak adresu"} · próg: {feed.auto_import_after ? new Date(feed.auto_import_after).toLocaleString("pl-PL") : "brak"}</div>
        {feed.author_name && <div style={{ color: "#475569", fontSize: ".85rem", marginTop: 6 }}>Autor / kanał: {feed.author_name}</div>}
        {!!feed.default_topic_group_ids?.length && <div style={{ color: "#475569", fontSize: ".85rem", marginTop: 6 }}>Tematy domyślne: {contentGroups.filter(group => feed.default_topic_group_ids.includes(group.id)).map(group => group.name).join(", ")}</div>}
        {feed.last_error && <div style={{ color: "#b91c1c", marginTop: 8 }}>{feed.last_error}</div>}
      </article>)}
    </div>
    {!visibleFeeds.length && <p style={{ color: "#64748b", marginTop: 20 }}>Brak feedów.</p>}
  </section>;
}
