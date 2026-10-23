import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";
import type { ContentGroup, ContentGroupSuggestion } from "../../../../types";

// Priority group backing the ★ button; created once by the owner (kind=priority, rank 10).
const FAVORITE_GROUP_NAME = "Ulubione";

// How often and how many times a freshly requested suggestion run is polled for its result.
const SUGGESTION_POLL_MS = 4000;
const SUGGESTION_POLL_MAX = 15;

// autoSuggest: ask the backend to classify the target when it has no suggestion run yet (feed review).
// manualSuggest: show a "Zaproponuj temat" button that asks `suggestModel` (empty = the server default) on demand.
type Props ={ documentId?: number | string; feedItemId?: number; initialGroups?: ContentGroup[]; autoSuggest?: boolean; manualSuggest?: boolean; suggestModel?: string; onSaved?: (groups: ContentGroup[]) => void };

export default function ContentGroupsPanel({ documentId, feedItemId, initialGroups, autoSuggest, manualSuggest, suggestModel, onSaved }: Props) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [catalog, setCatalog] = React.useState<ContentGroup[]>([]);
  const [groups, setGroups] = React.useState<ContentGroup[]>(initialGroups || []);
  const [suggestions, setSuggestions] = React.useState<ContentGroupSuggestion[]>([]);
  const [editing, setEditing] = React.useState(false);
  const [topicIds, setTopicIds] = React.useState<number[]>([]);
  const [priorityId, setPriorityId] = React.useState<number | "">("");
  const [error, setError] = React.useState("");
  const [pendingRun, setPendingRun] = React.useState(false);
  const [newTopicName, setNewTopicName] = React.useState("");
  const [runModel, setRunModel] = React.useState("");
  const [runError, setRunError] = React.useState("");
  const requestedRef = React.useRef(false);
  const pollsRef = React.useRef(0);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "", "Content-Type": "application/json" }), [apiKey]);
  const target = documentId !== undefined ? `document/${documentId}` : `feed_items/${feedItemId}`;

  const load = React.useCallback(async () => {
    setError("");
    try {
      const groupResponse = await fetch(`${apiUrl}/content_groups`, { headers });
      if (!groupResponse.ok) throw new Error(`content_groups: HTTP ${groupResponse.status}`);
      const groupData = await groupResponse.json();
      setCatalog(Array.isArray(groupData.content_groups) ? groupData.content_groups : []);
      const currentResponse = await fetch(`${apiUrl}/${target}/groups`, { headers });
      if (!currentResponse.ok) throw new Error(`groups: HTTP ${currentResponse.status}`);
      const currentData = await currentResponse.json();
      const current = Array.isArray(currentData.groups) ? currentData.groups : [];
      setGroups(current);
      setTopicIds(current.filter((group: ContentGroup) => group.kind === "topic").map((group: ContentGroup) => group.id));
      const priority = current.find((group: ContentGroup) => group.kind === "priority");
      setPriorityId(priority?.id || "");
      const suggestionResponse = await fetch(`${apiUrl}/${target}/group-suggestions`, { headers });
      if (!suggestionResponse.ok) throw new Error(`group-suggestions: HTTP ${suggestionResponse.status}`);
      const suggestionData = await suggestionResponse.json();
      setSuggestions(Array.isArray(suggestionData.suggestions) ? suggestionData.suggestions : []);
      const runStatus: string | undefined = suggestionData.run?.status;
      setRunModel(suggestionData.run?.model || "");
      setRunError(runStatus === "error" ? String(suggestionData.run?.error || "Klasyfikacja nie powiodła się") : "");
      if (autoSuggest && !suggestionData.run && !requestedRef.current && groupData.content_groups?.some((group: ContentGroup) => group.kind === "topic")) {
        requestedRef.current = true;
        const requestResponse = await fetch(`${apiUrl}/${target}/group-suggestions`, { method: "POST", headers, body: "{}" });
        if (requestResponse.ok) setPendingRun(true);
      } else {
        setPendingRun(runStatus === "queued" || runStatus === "running");
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać grup"); }
  }, [apiUrl, headers, target, autoSuggest]);

  React.useEffect(() => { void load(); }, [load]);

  // Poll quietly until the queued classification finishes (or give up after a minute).
  React.useEffect(() => {
    if (!pendingRun || pollsRef.current >= SUGGESTION_POLL_MAX) return;
    const timer = window.setTimeout(() => { pollsRef.current += 1; void load(); }, SUGGESTION_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [pendingRun, load, suggestions]);

  const save = async () => {
    setError("");
    const response = await fetch(`${apiUrl}/${target}/groups`, { method: "PATCH", headers, body: JSON.stringify({ group_ids: [...topicIds, ...(priorityId === "" ? [] : [priorityId])] }) });
    const data = await response.json();
    if (!response.ok) { setError(data.message || data.error || "Nie udało się zapisać grup"); return; }
    const next = data.groups || data.feed_item?.groups || [];
    setGroups(next); setEditing(false); onSaved?.(next);
  };

  // Creates a topic on the spot and ticks it, so a misclassified item can be fixed without leaving the page.
  const createTopic = async () => {
    const name = newTopicName.trim();
    if (!name) return;
    setError("");
    const response = await fetch(`${apiUrl}/content_groups`, { method: "POST", headers, body: JSON.stringify({ name, kind: "topic" }) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { setError(response.status === 409 ? "Temat o tej nazwie już istnieje" : data.message || data.error || "Nie udało się dodać tematu"); return; }
    setCatalog(items => [...items, data]);
    setTopicIds(ids => [...ids, data.id]);
    setNewTopicName("");
  };

  const favoriteGroup = catalog.find(group => group.kind === "priority" && group.name === FAVORITE_GROUP_NAME);
  const currentPriority = groups.find(group => group.kind === "priority");
  const isFavorite = !!favoriteGroup && currentPriority?.id === favoriteGroup.id;

  const toggleFavorite = async () => {
    if (!favoriteGroup) return;
    if (!isFavorite && currentPriority && !window.confirm(`Zastąpić priorytet „${currentPriority.name}” priorytetem „${favoriteGroup.name}”?`)) return;
    setError("");
    const topicGroupIds = groups.filter(group => group.kind === "topic").map(group => group.id);
    const response = await fetch(`${apiUrl}/${target}/groups`, { method: "PATCH", headers, body: JSON.stringify({ group_ids: [...topicGroupIds, ...(isFavorite ? [] : [favoriteGroup.id])] }) });
    const data = await response.json();
    if (!response.ok) { setError(data.message || data.error || "Nie udało się zapisać ulubionych"); return; }
    const next: ContentGroup[] = data.groups || data.feed_item?.groups || [];
    setGroups(next);
    setPriorityId(next.find(group => group.kind === "priority")?.id || "");
    onSaved?.(next);
  };

  // One explicit request for this item with the model chosen on the page; always a fresh run (force).
  const requestSuggestion = async () => {
    setError("");
    setRunError("");
    const response = await fetch(`${apiUrl}/${target}/group-suggestions`, {
      method: "POST", headers, body: JSON.stringify({ force: true, ...(suggestModel ? { model: suggestModel } : {}) }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      setError(data.message || data.error || `Nie udało się zlecić propozycji (HTTP ${response.status})`);
      return;
    }
    pollsRef.current = 0;
    setPendingRun(true);
    void load();
  };

  const decide = async (id: number, action: "accept" | "dismiss" | "revert") => {
    const response = await fetch(`${apiUrl}/content_group_suggestions/${id}/${action}`, { method: "POST", headers });
    if (response.ok) void load(); else setError("Nie udało się wykonać decyzji sugestii");
  };

  const topics = catalog.filter(group => group.kind === "topic");
  const priorities = catalog.filter(group => group.kind === "priority");
  return <section aria-label="Grupy materiału" style={{ border: "1px solid #dbe4ee", borderRadius: 8, padding: 12, marginBottom: 16 }}>
    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      {favoriteGroup && <button type="button" onClick={() => void toggleFavorite()} aria-pressed={isFavorite} title={isFavorite ? "Usuń z ulubionych" : "Dodaj do ulubionych"} style={{ fontSize: "1.3em", lineHeight: 1, background: "none", border: "none", cursor: "pointer", color: isFavorite ? "#f59e0b" : "#94a3b8" }}>{isFavorite ? "★" : "☆"}</button>}
      <strong>Grupy</strong>
      {groups.filter(group => group.kind === "priority").map(group => <span key={group.id} style={{ background: "#dbeafe", borderRadius: 12, padding: "2px 8px" }}>{group.name}</span>)}
      {groups.filter(group => group.kind === "topic").map(group => <span key={group.id} style={{ background: "#f1f5f9", borderRadius: 12, padding: "2px 8px" }}>{group.name}</span>)}
      {!groups.some(group => group.kind === "priority") && <span style={{ color: "#64748b" }}>Brak priorytetu</span>}
      <button type="button" onClick={() => setEditing(value => !value)}>{editing ? "Anuluj" : "Edytuj"}</button>
      {manualSuggest && <button type="button" disabled={pendingRun} onClick={() => void requestSuggestion()} title="Zapytaj model o temat dla tego wpisu">🤖 Zaproponuj temat</button>}
    </div>
    {editing && <div style={{ marginTop: 10 }}>
      <fieldset><legend>Tematy</legend>{topics.map(group => <label key={group.id} style={{ display: "inline-block", marginRight: 10 }}><input type="checkbox" checked={topicIds.includes(group.id)} onChange={event => setTopicIds(ids => event.target.checked ? [...ids, group.id] : ids.filter(id => id !== group.id))} /> {group.name}</label>)}</fieldset>
      <div style={{ margin: "6px 0" }}>
        <input aria-label="Nowy temat" placeholder="Nowy temat, np. Smart home" value={newTopicName} onChange={event => setNewTopicName(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); void createTopic(); } }} />{" "}
        <button type="button" disabled={!newTopicName.trim()} onClick={() => void createTopic()}>Dodaj temat</button>
      </div>
      <label>Priorytet <select value={priorityId} onChange={event => setPriorityId(event.target.value ? Number(event.target.value) : "")}><option value="">Brak priorytetu</option>{priorities.map(group => <option key={group.id} value={group.id}>{group.name} ({group.priority_rank})</option>)}</select></label>{" "}
      <button type="button" className="button" onClick={() => void save()}>Zapisz</button>
    </div>}
    {pendingRun && <div style={{ marginTop: 8, fontSize: "0.85em", color: "#64748b" }}>🤖 Szukam kategorii…</div>}
    {runError && !pendingRun && <p role="alert" className="errorText">Propozycja nie powiodła się{runModel ? ` (${runModel})` : ""}: {runError}</p>}
    {manualSuggest && !pendingRun && !runError && runModel && suggestions.length === 0 && <div style={{ marginTop: 8, fontSize: "0.85em", color: "#64748b" }}>🤖 {runModel}: brak pasującego tematu.</div>}
    {suggestions.filter(item => item.status === "pending").map(item => <div key={item.id} style={{ marginTop: 8, border: "1px dashed #64748b", padding: 6 }}><span>Sugestia: {catalog.find(group => group.id === item.group_id)?.name || item.group_id} ({Math.round(item.confidence * 100)}%){runModel ? ` · ${runModel}` : ""}</span>{item.reason && <div style={{ fontSize: "0.85em", color: "#475569" }}>{item.reason}</div>}{" "}<button type="button" onClick={() => void decide(item.id, "accept")}>Akceptuj</button>{" "}<button type="button" onClick={() => void decide(item.id, "dismiss")}>Odrzuć</button></div>)}
    {suggestions.filter(item => item.status === "accepted").map(item => <div key={item.id} style={{ marginTop: 8, fontSize: "0.85em", color: "#475569" }}>
      <span>{item.decided_by_user_id ? "👤" : "🤖"} {catalog.find(group => group.id === item.group_id)?.name || item.group_id} — {Math.round(item.confidence * 100)}%{item.reason ? `: ${item.reason}` : ""}</span>{" "}
      <button type="button" onClick={() => void decide(item.id, "revert")}>Cofnij</button>
    </div>)}
    {error && <p role="alert" className="errorText">{error}</p>}
  </section>;
}
