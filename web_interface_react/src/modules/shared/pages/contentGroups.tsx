import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

type Topic = {
  id: number; name: string; kind: string;
  saved_item_count: number; document_count: number; chunk_count: number; provenance_item_count: number;
};
type Pending = { kind: "delete" | "merge"; id: number };

const TIMEOUT_MS = 20_000;
const fold = (text: string) => text.toLocaleLowerCase("pl").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
const inUse = (topic: Topic) => topic.document_count + topic.chunk_count + topic.saved_item_count > 0;

async function request(url: string, init: RequestInit): Promise<{ status: number; data: Record<string, unknown> }> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const text = await response.text();
    let data: Record<string, unknown> = {};
    try { data = text ? JSON.parse(text) : {}; } catch { data = { message: text }; }
    return { status: response.status, data };
  } catch (cause) {
    if (controller.signal.aborted) throw new Error("Brak odpowiedzi z API — zmiana NIE została zapisana.");
    if (cause instanceof TypeError) throw new Error("Nie można połączyć się z API — zmiana NIE została zapisana.");
    throw cause;
  } finally { window.clearTimeout(timer); }
}

const failure = (status: number, data: Record<string, unknown>, fallback: string) => {
  if (status === 409 && /name already exists/.test(String(data.message || data.error))) return "Temat o takiej nazwie już istnieje.";
  if (status === 409 && data.error === "group is in active use") return "Temat jest w użyciu — scal go z innym tematem zamiast usuwać.";
  return String(data.message || data.error || fallback);
};

export default function ContentGroups() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "", "Content-Type": "application/json" }), [apiKey]);
  const [topics, setTopics] = React.useState<Topic[]>([]);
  const [filter, setFilter] = React.useState("");
  const [newName, setNewName] = React.useState("");
  const [editId, setEditId] = React.useState<number | null>(null);
  const [editName, setEditName] = React.useState("");
  const [pending, setPending] = React.useState<Pending | null>(null);
  const [mergeTarget, setMergeTarget] = React.useState<Record<number, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const [message, setMessage] = React.useState("");

  const load = React.useCallback(async () => {
    try {
      const { status, data } = await request(`${apiUrl}/content_groups`, { headers });
      if (status !== 200) throw new Error(failure(status, data, "Nie udało się pobrać tematów"));
      const list = (Array.isArray(data.content_groups) ? data.content_groups : []) as Topic[];
      setTopics(list.filter(group => group.kind === "topic"));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać tematów"); }
    finally { setLoaded(true); }
  }, [apiUrl, headers]);

  React.useEffect(() => { void load(); }, [load]);

  const run = async (action: () => Promise<string>) => {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try { setMessage(await action()); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Operacja nie powiodła się"); }
    finally { setBusy(false); }
  };

  const add = () => run(async () => {
    const name = newName.trim();
    const { status, data } = await request(`${apiUrl}/content_groups`, { method: "POST", headers, body: JSON.stringify({ name, kind: "topic" }) });
    if (status !== 201) throw new Error(failure(status, data, "Nie udało się dodać tematu"));
    setNewName("");
    return `Dodano temat „${name}”.`;
  });

  const rename = (topic: Topic) => run(async () => {
    const name = editName.trim();
    if (name === topic.name) { setEditId(null); return ""; }
    const { status, data } = await request(`${apiUrl}/content_groups/${topic.id}`, { method: "PATCH", headers, body: JSON.stringify({ name }) });
    if (status !== 200) throw new Error(failure(status, data, "Nie udało się zmienić nazwy"));
    setEditId(null);
    return `Zmieniono nazwę „${topic.name}” na „${name}”. Dotyczy to od razu wszystkich oznaczonych materiałów.`;
  });

  const remove = (topic: Topic) => run(async () => {
    const { status, data } = await request(`${apiUrl}/content_groups/${topic.id}`, { method: "DELETE", headers });
    if (status !== 200) throw new Error(failure(status, data, "Nie udało się usunąć tematu"));
    setPending(null);
    return `Usunięto temat „${topic.name}” (trafił do archiwum).`;
  });

  const merge = (topic: Topic, target: Topic) => run(async () => {
    const { status, data } = await request(`${apiUrl}/content_groups/${topic.id}/merge`, { method: "POST", headers, body: JSON.stringify({ target_id: target.id }) });
    if (status !== 200) throw new Error(failure(status, data, "Nie udało się scalić tematów"));
    const moved = (data.moved || {}) as Record<string, number>;
    setPending(null);
    return `Scalono „${topic.name}” z „${target.name}”: przeniesiono ${moved.documents ?? 0} dok., ${moved.chunks ?? 0} fragm., ${moved.feed_items ?? 0} wpisów feedu. Temat „${topic.name}” zarchiwizowano.`;
  });

  const visible = topics.filter(topic => !filter.trim() || fold(topic.name).includes(fold(filter)));

  return <div style={{ padding: "0 16px 32px", maxWidth: 1000 }}>
    <h1>Tematy</h1>
    <p style={{ color: "#475569" }}>
      Katalog tematów używany w Kuracji feedów, dokumentach i rozdziałach. Zmiana nazwy działa od razu na wszystkich oznaczonych materiałach.
      Usunąć (zarchiwizować) można temat, pod którym nic nie jest zapisane; temat w użyciu najpierw <strong>scal</strong> z innym — jego materiały przejdą do wskazanego tematu.
    </p>

    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    {message && <p role="status" style={{ color: "#166534" }}>{message}</p>}

    <form onSubmit={event => { event.preventDefault(); if (newName.trim()) void add(); }} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", margin: "12px 0" }}>
      <label htmlFor="new-topic">Nowy temat:</label>
      <input id="new-topic" value={newName} maxLength={80} onChange={event => setNewName(event.target.value)} placeholder="np. Agenci AI" disabled={busy} />
      <button type="submit" disabled={busy || !newName.trim()}>Dodaj temat</button>
      <label htmlFor="topic-filter" style={{ marginLeft: 16 }}>Szukaj:</label>
      <input id="topic-filter" value={filter} onChange={event => setFilter(event.target.value)} placeholder="część nazwy" />
    </form>

    {loaded && !visible.length && <p>{topics.length ? "Żaden temat nie pasuje do wyszukiwania." : "Brak tematów."}</p>}
    {visible.length > 0 && <div style={{ overflowX: "auto" }}><table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead><tr style={{ textAlign: "left", borderBottom: "2px solid #cbd5e1" }}>
        <th>Temat</th><th>Dokumenty</th><th>Fragmenty</th><th title="Wpisy feedu zapisane na później">Zapisane wpisy</th><th>Działania</th>
      </tr></thead>
      <tbody>{visible.map(topic => {
        const others = topics.filter(other => other.id !== topic.id);
        const target = others.find(other => String(other.id) === mergeTarget[topic.id]);
        const used = inUse(topic);
        return <tr key={topic.id} style={{ borderBottom: "1px solid #e2e8f0", verticalAlign: "top" }}>
          <td style={{ padding: "6px 8px 6px 0" }}>{editId === topic.id
            ? <form onSubmit={event => { event.preventDefault(); if (editName.trim()) void rename(topic); }} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <input aria-label={`Nowa nazwa tematu ${topic.name}`} autoFocus value={editName} maxLength={80} disabled={busy}
                onChange={event => setEditName(event.target.value)} onKeyDown={event => { if (event.key === "Escape") setEditId(null); }} />
              <button type="submit" disabled={busy || !editName.trim()}>Zapisz</button>
              <button type="button" onClick={() => setEditId(null)}>Anuluj</button>
            </form>
            : <strong>{topic.name}</strong>}
          </td>
          <td>{topic.document_count}</td><td>{topic.chunk_count}</td><td>{topic.saved_item_count}</td>
          <td>
            {pending?.id === topic.id && pending.kind === "delete" && <span>
              Usunąć „{topic.name}”? <button type="button" disabled={busy} onClick={() => void remove(topic)}>Tak, usuń</button>{" "}
              <button type="button" onClick={() => setPending(null)}>Anuluj</button>
            </span>}
            {pending?.id === topic.id && pending.kind === "merge" && target && <span>
              Przenieść {topic.document_count} dok., {topic.chunk_count} fragm., {topic.provenance_item_count} wpisów feedu do „{target.name}” i zarchiwizować „{topic.name}”?{" "}
              <button type="button" disabled={busy} onClick={() => void merge(topic, target)}>Tak, scal</button>{" "}
              <button type="button" onClick={() => setPending(null)}>Anuluj</button>
            </span>}
            {pending?.id !== topic.id && <span style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <button type="button" disabled={busy} onClick={() => { setEditId(topic.id); setEditName(topic.name); setPending(null); }}>Zmień nazwę</button>
              <button type="button" disabled={busy || used} title={used ? "Temat jest w użyciu — scal go z innym tematem" : "Przenosi temat do archiwum"}
                onClick={() => { setPending({ kind: "delete", id: topic.id }); setEditId(null); }}>Usuń</button>
              <select aria-label={`Scal „${topic.name}” z…`} value={mergeTarget[topic.id] || ""} disabled={busy || !others.length}
                onChange={event => setMergeTarget(state => ({ ...state, [topic.id]: event.target.value }))}>
                <option value="">Scal z…</option>
                {others.map(other => <option key={other.id} value={other.id}>{other.name}</option>)}
              </select>
              <button type="button" disabled={busy || !target} onClick={() => { setPending({ kind: "merge", id: topic.id }); setEditId(null); }}>Scal</button>
            </span>}
          </td>
        </tr>;
      })}</tbody>
    </table></div>}
  </div>;
}
