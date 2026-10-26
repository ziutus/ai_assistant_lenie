import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

type Topic = {
  id: number; name: string; kind: string; retention_months: number | null; parent_id: number | null; description?: string | null;
  saved_item_count: number; document_count: number; chunk_count: number; provenance_item_count: number;
};
type Pending = { kind: "delete" | "merge"; id: number };
type Retention = { default_months: number; saved: boolean; built_in_months: number; min: number; max: number };
type DueItem = { id: number; title: string; saved_at: string; expires_at: string; months: number };
type Due = { dry_run: boolean; due: number; expired: number; items: DueItem[] };

const TIMEOUT_MS = 20_000;
const fold = (text: string) => text.toLocaleLowerCase("pl").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
const inUse = (topic: Topic) => topic.document_count + topic.chunk_count + topic.saved_item_count > 0;

function topicTree(topics: Topic[]) {
  const ids = new Set(topics.map(topic => topic.id));
  const result: { topic: Topic; depth: number; ancestors: number[] }[] = [];
  const seen = new Set<number>();
  const visit = (items: Topic[], ancestors: number[]) => {
    for (const topic of [...items].sort((a, b) => fold(a.name).localeCompare(fold(b.name)))) {
      if (seen.has(topic.id)) continue;
      seen.add(topic.id);
      result.push({ topic, depth: ancestors.length, ancestors });
      visit(topics.filter(child => child.parent_id === topic.id), [...ancestors, topic.id]);
    }
  };
  visit(topics.filter(topic => topic.parent_id == null || !ids.has(topic.parent_id)), []);
  return result;
}

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
  const hierarchyErrors: Record<string, string> = {
    "a topic cannot be its own ancestor": "Temat nie może być swoim własnym przodkiem.",
    "topic hierarchy is limited to 3 levels": "Hierarchia może mieć najwyżej 3 poziomy.",
    "parent must be an active topic": "Temat nadrzędny musi być aktywnym tematem.",
  };
  const hierarchyError = hierarchyErrors[String(data.message || data.error)];
  if (hierarchyError) return hierarchyError;
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
  const [newParent, setNewParent] = React.useState("");
  const [newDescription, setNewDescription] = React.useState("");
  const [descriptionDraft, setDescriptionDraft] = React.useState<Record<number, string>>({});
  const [parentDraft, setParentDraft] = React.useState<Record<number, string>>({});
  const [editId, setEditId] = React.useState<number | null>(null);
  const [editName, setEditName] = React.useState("");
  const [pending, setPending] = React.useState<Pending | null>(null);
  const [mergeTarget, setMergeTarget] = React.useState<Record<number, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [retention, setRetention] = React.useState<Retention | null>(null);
  const [defaultDraft, setDefaultDraft] = React.useState("");
  const [retentionDraft, setRetentionDraft] = React.useState<Record<number, string>>({});
  const [due, setDue] = React.useState<Due | null>(null);

  const load = React.useCallback(async () => {
    try {
      const { status, data } = await request(`${apiUrl}/content_groups`, { headers });
      if (status !== 200) throw new Error(failure(status, data, "Nie udało się pobrać tematów"));
      const list = (Array.isArray(data.content_groups) ? data.content_groups : []) as Topic[];
      setTopics(list.filter(group => group.kind === "topic"));
      const settings = await request(`${apiUrl}/feed_items/retention`, { headers });
      if (settings.status === 200 && typeof settings.data.default_months === "number") {
        const loadedRetention = settings.data as unknown as Retention;
        setRetention(loadedRetention);
        setDefaultDraft(current => current || String(loadedRetention.default_months));
      }
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
    const description = newDescription.trim();
    const { status, data } = await request(`${apiUrl}/content_groups`, { method: "POST", headers, body: JSON.stringify({ name, kind: "topic", ...(newParent ? { parent_id: Number(newParent) } : {}), ...(description ? { description } : {}) }) });
    if (status !== 201) throw new Error(failure(status, data, "Nie udało się dodać tematu"));
    setNewName("");
    setNewDescription("");
    setNewParent("");
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

  const saveDefaultRetention = (months: number | null) => run(async () => {
    const { status, data } = await request(`${apiUrl}/feed_items/retention`, { method: "PUT", headers, body: JSON.stringify({ default_months: months }) });
    if (status !== 200) throw new Error(failure(status, data, "Nie udało się zapisać domyślnej ważności"));
    setDefaultDraft(String(data.default_months));
    return months === null ? `Przywrócono domyślną ważność: ${data.default_months} mies.` : `Domyślna ważność wpisów „Może kiedyś”: ${data.default_months} mies.`;
  });

  const saveTopicRetention = (topic: Topic) => run(async () => {
    const draft = (retentionDraft[topic.id] ?? "").trim();
    const months = draft === "" ? null : Number(draft);
    const { status, data } = await request(`${apiUrl}/content_groups/${topic.id}`, { method: "PATCH", headers, body: JSON.stringify({ retention_months: months }) });
    if (status !== 200) throw new Error(failure(status, data, "Nie udało się zapisać ważności"));
    setRetentionDraft(state => { const next = { ...state }; delete next[topic.id]; return next; });
    return months === null ? `Temat „${topic.name}” używa ważności domyślnej.` : `Temat „${topic.name}”: wpisy „Może kiedyś” ważne ${months} mies.`;
  });

  const checkExpiry = (dryRun: boolean) => run(async () => {
    const { status, data } = await request(`${apiUrl}/feed_items/expire_saved`, { method: "POST", headers, body: JSON.stringify({ dry_run: dryRun }) });
    if (status !== 200) throw new Error(failure(status, data, "Nie udało się sprawdzić ważności wpisów"));
    const result = data as unknown as Due;
    setDue(dryRun ? result : null);
    if (dryRun) return result.due ? `Do przesunięcia do „Pomiń”: ${result.due}.` : "Żaden wpis „Może kiedyś” nie przekroczył terminu ważności.";
    return `Przesunięto do „Pomiń”: ${result.expired} z ${result.due} wpisów.`;
  });

  const clearDescriptionDraft = (id: number) => setDescriptionDraft(state => { const next = { ...state }; delete next[id]; return next; });
  const saveDescription = (topic: Topic) => run(async () => {
    const description = (descriptionDraft[topic.id] ?? "").trim();
    const { status, data } = await request(`${apiUrl}/content_groups/${topic.id}`, { method: "PATCH", headers, body: JSON.stringify({ description: description || null }) });
    if (status !== 200) throw new Error(failure(status, data, "Nie udało się zapisać opisu"));
    clearDescriptionDraft(topic.id);
    return description ? `Zapisano opis tematu „${topic.name}”. Model zobaczy go przy następnych podpowiedziach.` : `Usunięto opis tematu „${topic.name}”.`;
  });

  const clearParentDraft = (id: number) => setParentDraft(state => { const next = { ...state }; delete next[id]; return next; });
  const saveParent = (topic: Topic) => run(async () => {
    const parent_id = parentDraft[topic.id] ? Number(parentDraft[topic.id]) : null;
    const { status, data } = await request(`${apiUrl}/content_groups/${topic.id}`, { method: "PATCH", headers, body: JSON.stringify({ parent_id }) });
    if (status !== 200) throw new Error(failure(status, data, "Nie udało się zapisać tematu nadrzędnego"));
    clearParentDraft(topic.id);
    return parent_id === null ? `Temat „${topic.name}” jest tematem głównym.`
      : `Temat „${topic.name}” jest teraz podtematem „${topics.find(parent => parent.id === parent_id)?.name}”.`;
  });
  const tree = topicTree(topics);
  const visible = tree.filter(({ topic }) => !filter.trim() || fold(topic.name).includes(fold(filter)));

  return <div style={{ padding: "0 16px 32px", maxWidth: 1000 }}>
    <h1>Tematy</h1>
    <p style={{ color: "#475569" }}>
      Katalog tematów używany w Kuracji feedów, dokumentach i rozdziałach. Zmiana nazwy działa od razu na wszystkich oznaczonych materiałach.
      Usunąć (zarchiwizować) można temat, pod którym nic nie jest zapisane; temat w użyciu najpierw <strong>scal</strong> z innym — jego materiały przejdą do wskazanego tematu.
    </p>

    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    {message && <p role="status" style={{ color: "#166534" }}>{message}</p>}

    <section aria-label="Ważność wpisów Może kiedyś" style={{ border: "1px solid #e2e8f0", padding: "8px 12px", margin: "12px 0" }}>
      <strong>Ważność wpisów „Może kiedyś”</strong>
      <p style={{ margin: "4px 0", color: "#475569" }}>
        Wpis zapisany przyciskiem „Może kiedyś” po tylu miesiącach od zapisania sam przechodzi do „Pomiń” (powód: wygasł) — sprawdza to codzienne zadanie o 4:00.
        Dla wpisu z kilkoma tematami liczy się najdłuższa ważność. Temat bez własnej wartości używa domyślnej.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <label htmlFor="default-retention">Domyślnie (mies.):</label>
        <input id="default-retention" type="number" min={retention?.min ?? 1} max={retention?.max ?? 120} style={{ width: 70 }} value={defaultDraft}
          onChange={event => setDefaultDraft(event.target.value)} disabled={busy} />
        <button type="button" disabled={busy || !defaultDraft || Number(defaultDraft) === retention?.default_months}
          onClick={() => void saveDefaultRetention(Number(defaultDraft))}>Zapisz domyślną</button>
        {retention?.saved && <button type="button" disabled={busy} onClick={() => void saveDefaultRetention(null)}>Przywróć {retention.built_in_months} mies.</button>}
        <button type="button" disabled={busy} onClick={() => void checkExpiry(true)}>Sprawdź, co wygasło</button>
        {due && due.due > 0 && <button type="button" disabled={busy} onClick={() => void checkExpiry(false)}>Przesuń {due.due} do „Pomiń” teraz</button>}
      </div>
      {due && due.items.length > 0 && <ul style={{ margin: "6px 0 0" }}>{due.items.map(entry => <li key={entry.id}>{entry.title} <small style={{ color: "#64748b" }}>(zapisano {entry.saved_at.slice(0, 10)}, ważne było do {entry.expires_at.slice(0, 10)})</small></li>)}</ul>}
    </section>

    <form onSubmit={event => { event.preventDefault(); if (newName.trim()) void add(); }} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", margin: "12px 0" }}>
      <label htmlFor="new-topic">Nowy temat:</label>
      <input id="new-topic" value={newName} maxLength={80} onChange={event => setNewName(event.target.value)} placeholder="np. Agenci AI" disabled={busy} />
      <label htmlFor="new-topic-parent">Pod tematem:</label>
      <select id="new-topic-parent" value={newParent} onChange={event => setNewParent(event.target.value)} disabled={busy}>
        <option value="">— temat główny —</option>
        {tree.filter(entry => entry.depth < 2).map(({ topic }) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}
      </select>
      <label htmlFor="new-topic-description">Opis:</label>
      <input id="new-topic-description" value={newDescription} maxLength={300} style={{ minWidth: 260 }} onChange={event => setNewDescription(event.target.value)}
        placeholder="zakres tematu, widoczny dla modelu (opcjonalnie)" disabled={busy} />
      <button type="submit" disabled={busy || !newName.trim()}>Dodaj temat</button>
      <label htmlFor="topic-filter" style={{ marginLeft: 16 }}>Szukaj:</label>
      <input id="topic-filter" value={filter} onChange={event => setFilter(event.target.value)} placeholder="część nazwy" />
    </form>

    {loaded && !visible.length && <p>{topics.length ? "Żaden temat nie pasuje do wyszukiwania." : "Brak tematów."}</p>}
    {visible.length > 0 && <div style={{ overflowX: "auto" }}><table style={{ borderCollapse: "collapse", width: "100%" }}>
      <thead><tr style={{ textAlign: "left", borderBottom: "2px solid #cbd5e1" }}>
        <th>Temat</th><th>Temat nadrzędny</th><th title="Zakres tematu wysyłany do modelu razem z nazwą — pomaga w niejednoznacznych nazwach.">Opis dla modelu</th><th>Dokumenty</th><th>Fragmenty</th><th title="Wpisy feedu zapisane na później">Zapisane wpisy</th>
        <th title="Po ilu miesiącach wpis „Może kiedyś” z tym tematem przechodzi do „Pomiń”. Puste = domyślnie.">Ważność (mies.)</th><th>Działania</th>
      </tr></thead>
      <tbody>{visible.map(({ topic, depth }) => {
        const others = topics.filter(other => other.id !== topic.id);
        const target = others.find(other => String(other.id) === mergeTarget[topic.id]);
        const used = inUse(topic);
        return <tr key={topic.id} style={{ borderBottom: "1px solid #e2e8f0", verticalAlign: "top" }}>
          <td style={{ padding: "6px 8px 6px 0", paddingLeft: depth * 20 }}>{depth > 0 && "↳ "}{editId === topic.id
            ? <form onSubmit={event => { event.preventDefault(); if (editName.trim()) void rename(topic); }} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <input aria-label={`Nowa nazwa tematu ${topic.name}`} autoFocus value={editName} maxLength={80} disabled={busy}
                onChange={event => setEditName(event.target.value)} onKeyDown={event => { if (event.key === "Escape") setEditId(null); }} />
              <button type="submit" disabled={busy || !editName.trim()}>Zapisz</button>
              <button type="button" onClick={() => setEditId(null)}>Anuluj</button>
            </form>
            : <strong>{topic.name}</strong>}
          </td>
          <td>
            <select aria-label={`Temat nadrzędny dla ${topic.name}`} disabled={busy}
              value={parentDraft[topic.id] ?? String(topic.parent_id ?? "")}
              onChange={event => setParentDraft(state => ({ ...state, [topic.id]: event.target.value }))}>
              <option value="">— temat główny —</option>
              {tree.filter(entry => entry.topic.id !== topic.id && !entry.ancestors.includes(topic.id) && entry.depth < 2)
                .map(({ topic: parent }) => <option key={parent.id} value={parent.id}>{parent.name}</option>)}
            </select>
            {parentDraft[topic.id] !== undefined && parentDraft[topic.id] !== String(topic.parent_id ?? "") && <>
              <button type="button" disabled={busy} onClick={() => void saveParent(topic)}>Zapisz</button>{" "}
              <button type="button" onClick={() => clearParentDraft(topic.id)}>Anuluj</button>
            </>}
          </td>
          <td>
            <textarea aria-label={`Opis tematu ${topic.name}`} rows={2} maxLength={300} style={{ width: 240 }} disabled={busy}
              placeholder="np. kradzież tożsamości, wycieki danych, oszustwa na PESEL"
              value={descriptionDraft[topic.id] ?? (topic.description ?? "")}
              onChange={event => setDescriptionDraft(state => ({ ...state, [topic.id]: event.target.value }))} />
            {descriptionDraft[topic.id] !== undefined && descriptionDraft[topic.id] !== (topic.description ?? "") && <>
              <button type="button" disabled={busy} onClick={() => void saveDescription(topic)}>Zapisz</button>{" "}
              <button type="button" onClick={() => clearDescriptionDraft(topic.id)}>Anuluj</button>
            </>}
          </td>
          <td>{topic.document_count}</td><td>{topic.chunk_count}</td><td>{topic.saved_item_count}</td>
          <td style={{ whiteSpace: "nowrap" }}>
            <input type="number" aria-label={`Ważność wpisów „Może kiedyś” dla tematu ${topic.name} (miesiące)`} style={{ width: 64 }}
              min={retention?.min ?? 1} max={retention?.max ?? 120} placeholder={String(retention?.default_months ?? "")} disabled={busy}
              value={retentionDraft[topic.id] ?? (topic.retention_months ?? "")}
              onChange={event => setRetentionDraft(state => ({ ...state, [topic.id]: event.target.value }))} />{" "}
            {retentionDraft[topic.id] !== undefined && retentionDraft[topic.id] !== String(topic.retention_months ?? "") && <>
              <button type="button" disabled={busy} onClick={() => void saveTopicRetention(topic)}>Zapisz</button>{" "}
              <button type="button" onClick={() => setRetentionDraft(state => { const next = { ...state }; delete next[topic.id]; return next; })}>Anuluj</button>
            </>}
          </td>
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
