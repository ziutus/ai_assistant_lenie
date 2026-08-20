import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";
import type { ContentGroup, ContentGroupSuggestion } from "../../../../types";

type Props = { documentId?: number | string; feedItemId?: number; initialGroups?: ContentGroup[]; onSaved?: (groups: ContentGroup[]) => void };

export default function ContentGroupsPanel({ documentId, feedItemId, initialGroups, onSaved }: Props) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [catalog, setCatalog] = React.useState<ContentGroup[]>([]);
  const [groups, setGroups] = React.useState<ContentGroup[]>(initialGroups || []);
  const [suggestions, setSuggestions] = React.useState<ContentGroupSuggestion[]>([]);
  const [editing, setEditing] = React.useState(false);
  const [topicIds, setTopicIds] = React.useState<number[]>([]);
  const [priorityId, setPriorityId] = React.useState<number | "">("");
  const [error, setError] = React.useState("");
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "", "Content-Type": "application/json" }), [apiKey]);
  const target = documentId !== undefined ? `document/${documentId}` : `feed_items/${feedItemId}`;

  const load = React.useCallback(async () => {
    try {
      const groupResponse = await fetch(`${apiUrl}/content_groups`, { headers });
      const groupData = await groupResponse.json();
      setCatalog(Array.isArray(groupData.content_groups) ? groupData.content_groups : []);
      const currentResponse = await fetch(`${apiUrl}/${target}/groups`, { headers });
      const currentData = await currentResponse.json();
      const current = Array.isArray(currentData.groups) ? currentData.groups : [];
      setGroups(current);
      setTopicIds(current.filter((group: ContentGroup) => group.kind === "topic").map((group: ContentGroup) => group.id));
      const priority = current.find((group: ContentGroup) => group.kind === "priority");
      setPriorityId(priority?.id || "");
      const suggestionResponse = await fetch(`${apiUrl}/${target}/group-suggestions`, { headers });
      const suggestionData = await suggestionResponse.json();
      setSuggestions(Array.isArray(suggestionData.suggestions) ? suggestionData.suggestions : []);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać grup"); }
  }, [apiUrl, headers, target]);

  React.useEffect(() => { void load(); }, [load]);

  const save = async () => {
    setError("");
    const response = await fetch(`${apiUrl}/${target}/groups`, { method: "PATCH", headers, body: JSON.stringify({ group_ids: [...topicIds, ...(priorityId === "" ? [] : [priorityId])] }) });
    const data = await response.json();
    if (!response.ok) { setError(data.message || data.error || "Nie udało się zapisać grup"); return; }
    const next = data.groups || data.feed_item?.groups || [];
    setGroups(next); setEditing(false); onSaved?.(next);
  };

  const decide = async (id: number, action: "accept" | "dismiss" | "revert") => {
    const response = await fetch(`${apiUrl}/content_group_suggestions/${id}/${action}`, { method: "POST", headers });
    if (response.ok) void load(); else setError("Nie udało się wykonać decyzji sugestii");
  };

  const topics = catalog.filter(group => group.kind === "topic");
  const priorities = catalog.filter(group => group.kind === "priority");
  return <section aria-label="Grupy materiału" style={{ border: "1px solid #dbe4ee", borderRadius: 8, padding: 12, marginBottom: 16 }}>
    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <strong>Grupy</strong>
      {groups.filter(group => group.kind === "priority").map(group => <span key={group.id} style={{ background: "#dbeafe", borderRadius: 12, padding: "2px 8px" }}>{group.name}</span>)}
      {groups.filter(group => group.kind === "topic").map(group => <span key={group.id} style={{ background: "#f1f5f9", borderRadius: 12, padding: "2px 8px" }}>{group.name}</span>)}
      {!groups.some(group => group.kind === "priority") && <span style={{ color: "#64748b" }}>Brak priorytetu</span>}
      <button type="button" onClick={() => setEditing(value => !value)}>{editing ? "Anuluj" : "Edytuj"}</button>
    </div>
    {editing && <div style={{ marginTop: 10 }}>
      <fieldset><legend>Tematy</legend>{topics.map(group => <label key={group.id} style={{ display: "inline-block", marginRight: 10 }}><input type="checkbox" checked={topicIds.includes(group.id)} onChange={event => setTopicIds(ids => event.target.checked ? [...ids, group.id] : ids.filter(id => id !== group.id))} /> {group.name}</label>)}</fieldset>
      <label>Priorytet <select value={priorityId} onChange={event => setPriorityId(event.target.value ? Number(event.target.value) : "")}><option value="">Brak priorytetu</option>{priorities.map(group => <option key={group.id} value={group.id}>{group.name} ({group.priority_rank})</option>)}</select></label>{" "}
      <button type="button" className="button" onClick={() => void save()}>Zapisz</button>
    </div>}
    {suggestions.filter(item => item.status === "pending").map(item => <div key={item.id} style={{ marginTop: 8, border: "1px dashed #64748b", padding: 6 }}><span>Sugestia: {catalog.find(group => group.id === item.group_id)?.name || item.group_id} ({Math.round(item.confidence * 100)}%)</span>{" "}<button type="button" onClick={() => void decide(item.id, "accept")}>Akceptuj</button>{" "}<button type="button" onClick={() => void decide(item.id, "dismiss")}>Odrzuć</button></div>)}
    {suggestions.filter(item => item.status === "accepted").map(item => <div key={item.id} style={{ marginTop: 8, fontSize: "0.85em", color: "#475569" }}>
      <span>{item.decided_by_user_id ? "👤" : "🤖"} {catalog.find(group => group.id === item.group_id)?.name || item.group_id} — {Math.round(item.confidence * 100)}%{item.reason ? `: ${item.reason}` : ""}</span>{" "}
      <button type="button" onClick={() => void decide(item.id, "revert")}>Cofnij</button>
    </div>)}
    {error && <p role="alert" className="errorText">{error}</p>}
  </section>;
}
