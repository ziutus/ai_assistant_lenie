import React from "react";
import axios from "axios";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

const sections = {
  document: "Dokumenty", contact: "Kontakty", chat_conversation: "Czaty", chat_message: "Wiadomości",
};
type EntityType = keyof typeof sections;
interface TopicItem {
  id: number;
  entity_id: number;
  note: string | null;
  entity: { id: number; title?: string; url?: string; display_name?: string; content?: string;
    sent_at?: string; conversation_id?: number } | null;
}
interface Topic {
  id: number;
  name: string;
  description: string | null;
  archived_at: string | null;
  items?: Record<EntityType, TopicItem[]>;
}
const errorText = (error: unknown) => axios.isAxiosError(error)
  ? error.response?.data?.message || error.message : "Nie udało się wykonać operacji";

function useTopicsApi() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  return React.useMemo(() => axios.create({ baseURL: apiUrl, headers: { "x-api-key": `${apiKey}` } }), [apiUrl, apiKey]);
}

export default function Topics() {
  const api = useTopicsApi();
  const [params, setParams] = useSearchParams();
  const archived = params.get("include_archived") === "1";
  const requestedPage = Number(params.get("page") || 1);
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const requestedSize = Number(params.get("page_size") || 50);
  const pageSize = PAGE_SIZES.includes(requestedSize) ? requestedSize : 50;
  const [topics, setTopics] = React.useState<Topic[]>([]);
  const [total, setTotal] = React.useState(0);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [version, refresh] = React.useReducer(n => n + 1, 0);
  React.useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError("");
    api.get("/topics", { params: { include_archived: archived ? 1 : 0, limit: pageSize, offset: (page - 1) * pageSize },
      signal: controller.signal }).then(({ data }) => { setTopics(data.topics); setTotal(data.total); })
      .catch(err => { if (!controller.signal.aborted) setError(errorText(err)); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [api, archived, page, pageSize, version]);
  const changeParams = (values: Record<string, string>) => setParams(previous => {
    const next = new URLSearchParams(previous);
    Object.entries(values).forEach(([key, value]) => next.set(key, value));
    return next;
  });
  const create = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api.post("/topics", { name, description });
      setName(""); setDescription(""); changeParams({ page: "1" }); refresh();
    } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };
  return <div style={{ padding: 20 }}>
    <h2>Tematy</h2>
    <label><input type="checkbox" checked={archived}
      onChange={e => changeParams({ include_archived: e.target.checked ? "1" : "0", page: "1" })} /> Pokaż archiwalne</label>
    <form onSubmit={create} style={{ display: "grid", gap: 8, maxWidth: 600, margin: "16px 0" }}>
      <h3>Nowy temat</h3>
      <label>Nazwa <input required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
      <label>Opis <textarea value={description} onChange={e => setDescription(e.target.value)} /></label>
      <button className="button" disabled={busy || !name.trim()}>Utwórz temat</button>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {busy && <p>Ładowanie…</p>}
    {!busy && !error && topics.length === 0 && <p>Brak tematów.</p>}
    <ul>{topics.map(topic => <li key={topic.id} style={{ marginBottom: 12 }}>
      <Link to={`/topics/${topic.id}`}>{topic.name}</Link>{topic.archived_at && " (archiwalny)"}
      {topic.description && <p>{topic.description}</p>}
    </li>)}</ul>
    <label>Na stronie <select value={pageSize} onChange={e => changeParams({ page_size: e.target.value, page: "1" })}>
      {PAGE_SIZES.map(size => <option key={size}>{size}</option>)}
    </select></label>
    <Pagination page={page} pageSize={pageSize} total={total} isLoading={busy} label="tematów"
      onPageChange={next => changeParams({ page: String(next) })} />
  </div>;
}

function entityLink(kind: EntityType, entity: NonNullable<TopicItem["entity"]>) {
  if (kind === "document") return `/read/${entity.id}`;
  if (kind === "contact") return `/contacts/${entity.id}`;
  if (kind === "chat_conversation") return `/chats/${entity.id}`;
  return `/chats/${entity.conversation_id}?date_from=${encodeURIComponent(entity.sent_at?.slice(0, 10) || "")}`;
}

export function TopicDetail() {
  const { id } = useParams();
  const api = useTopicsApi();
  const [topic, setTopic] = React.useState<Topic | null>(null);
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [kind, setKind] = React.useState<EntityType>("document");
  const [entityId, setEntityId] = React.useState("");
  const [note, setNote] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [version, refresh] = React.useReducer(n => n + 1, 0);
  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setTopic(null); setError("");
    api.get(`/topics/${id}`, { signal: controller.signal }).then(({ data }) => {
      setTopic(data.topic); setName(data.topic.name); setDescription(data.topic.description || "");
    }).catch(err => { if (!controller.signal.aborted) setError(errorText(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, id, version]);
  const mutate = async (action: () => Promise<unknown>) => {
    setBusy(true); setError("");
    try { await action(); refresh(); } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
  };
  return <div style={{ padding: 20 }}>
    <Link to="/topics">← Tematy</Link>
    {error && <p className="error" role="alert">{error}</p>}
    {loading && <p>Ładowanie…</p>}
    {topic && <>
      <h2>{topic.name}{topic.archived_at && " (archiwalny)"}</h2>
      <form onSubmit={event => { event.preventDefault(); void mutate(() => api.patch(`/topics/${id}`, { name, description })); }}>
        <fieldset disabled={busy} style={{ display: "grid", gap: 8, maxWidth: 600 }}>
          <legend>Edytuj temat</legend>
          <label>Nazwa <input required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
          <label>Opis <textarea value={description} onChange={e => setDescription(e.target.value)} /></label>
          <button className="button" disabled={!name.trim()}>Zapisz</button>
          <button type="button" className="button" onClick={() => void mutate(() => api.patch(`/topics/${id}`, { archived: !topic.archived_at }))}>
            {topic.archived_at ? "Przywróć temat" : "Archiwizuj temat"}</button>
        </fieldset>
      </form>
      <form onSubmit={event => { event.preventDefault(); void mutate(async () => {
        await api.post(`/topics/${id}/items`, { entity_type: kind, entity_id: Number(entityId), note: note || null });
        setEntityId(""); setNote("");
      }); }}>
        <fieldset disabled={busy} style={{ display: "grid", gap: 8, maxWidth: 600, marginTop: 16 }}>
          <legend>Dodaj powiązanie</legend>
          <label>Typ <select value={kind} onChange={e => setKind(e.target.value as EntityType)}>
            {Object.entries(sections).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select></label>
          <label>ID <input required type="number" min={1} max={2147483647} step={1} value={entityId} onChange={e => setEntityId(e.target.value)} /></label>
          <label>Notatka <input value={note} onChange={e => setNote(e.target.value)} /></label>
          <button className="button">Dodaj</button>
        </fieldset>
      </form>
      {(Object.keys(sections) as EntityType[]).map(type => <section key={type}>
        <h3>{sections[type]}</h3>
        {!topic.items?.[type].length && <p>Brak powiązań.</p>}
        <ul>{topic.items?.[type].map(item => <li key={item.id} style={{ marginBottom: 12 }}>
          {item.entity ? <Link to={entityLink(type, item.entity)}>
            {item.entity.title || item.entity.display_name || item.entity.content || `#${item.entity_id}`}
          </Link> : <span>Usunięty element #{item.entity_id}</span>}
          {item.entity?.sent_at && <time style={{ marginLeft: 8 }}>{item.entity.sent_at}</time>}
          {item.note && <p>{item.note}</p>}
          <button className="button" style={{ marginLeft: 8 }} disabled={busy}
            onClick={() => void mutate(() => api.delete(`/topic_items/${item.id}`))}>Usuń powiązanie</button>
        </li>)}</ul>
      </section>)}
    </>}
  </div>;
}
