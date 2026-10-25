import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";
import type { ContentGroup, ContentGroupSuggestion } from "../../../../types";

// Priority group backing the ★ button; created once by the owner (kind=priority, rank 10).
const FAVORITE_GROUP_NAME = "Ulubione";

// How often and how many times a freshly requested suggestion run is polled for its result.
const SUGGESTION_POLL_MS = 4000;
const SUGGESTION_POLL_MAX = 15;

// Feed review requests missing runs and replaces completed runs from a different model.
type NewTopic = { name: string; confidence: number; reason: string };
const foldName = (name: string) => name.trim().toLocaleLowerCase("pl").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ł/g, "l");

type PromptPreview = {
  model: string; prompt_version: string; structured: boolean; system_sent: boolean;
  system_prompt: string | null; prompt: string; response_format: unknown;
};

// Plain-text form of a preview, for pasting into a chat or an editor when working out why a prompt gave no answer.
const NL = String.fromCharCode(10);
export function promptPreviewText(preview: PromptPreview): string {
  const parts = [["# model: " + preview.model, "# prompt: " + preview.prompt_version].join(NL)];
  if (preview.system_prompt) parts.push("## System" + (preview.system_sent ? "" : " (nie jest wysyłany dla tego modelu)") + NL + NL + preview.system_prompt);
  parts.push("## Użytkownik" + NL + NL + preview.prompt);
  if (preview.response_format != null) parts.push("## response_format (schemat JSON)" + NL + NL + JSON.stringify(preview.response_format, null, 2));
  return parts.join(NL + NL);
}

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return; }
  const textarea = document.createElement("textarea");
  const focused = document.activeElement;
  textarea.value = text; textarea.style.position = "fixed"; textarea.style.opacity = "0";
  document.body.appendChild(textarea); textarea.select();
  try { if (!document.execCommand("copy")) throw new Error("copy failed"); }
  finally { document.body.removeChild(textarea); if (focused instanceof HTMLElement) focused.focus(); }
}

type Props ={ documentId?: number | string; feedItemId?: number; initialGroups?: ContentGroup[]; autoSuggest?: boolean; suggestModel?: string; templateId?: number; onModelCall?: () => void; onSaved?: (groups: ContentGroup[]) => void };

export default function ContentGroupsPanel({ documentId, feedItemId, initialGroups, autoSuggest, suggestModel, templateId, onModelCall, onSaved }: Props) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [catalog, setCatalog] = React.useState<ContentGroup[]>([]);
  const [groups, setGroups] = React.useState<ContentGroup[]>(initialGroups || []);
  const [suggestions, setSuggestions] = React.useState<ContentGroupSuggestion[]>([]);
  const [newTopics, setNewTopics] = React.useState<NewTopic[]>([]);
  const [dismissedTopics, setDismissedTopics] = React.useState<string[]>([]);
  const [creatingTopic, setCreatingTopic] = React.useState(false);
  const [editing, setEditing] = React.useState(false);
  const [topicIds, setTopicIds] = React.useState<number[]>([]);
  const [priorityId, setPriorityId] = React.useState<number | "">("");
  const [error, setError] = React.useState("");
  const [runModel, setRunModel] = React.useState("");
  const [runPrompt, setRunPrompt] = React.useState("");
  const [runError, setRunError] = React.useState("");
  const [runDone, setRunDone] = React.useState(false);
  const [promptPreview, setPromptPreview] = React.useState<PromptPreview | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [promptCopied, setPromptCopied] = React.useState(false);
  const [pendingRun, setPendingRun] = React.useState(false);
  const [newTopicName, setNewTopicName] = React.useState("");
  const requestedRef = React.useRef(new Set<string>());
  const awaitingModelRef = React.useRef<string | null>(null);
  const mountedRef = React.useRef(false);
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
      setRunModel(suggestionData.run?.model || "");
      setRunPrompt(suggestionData.run?.prompt_version || "");
      const runStatus: string | undefined = suggestionData.run?.status;
      setRunDone(runStatus === "completed");
      setRunError(runStatus === "error" ? String(suggestionData.run?.error || "Klasyfikacja nie powiodła się") : "");
      const running = runStatus === "queued" || runStatus === "running";
      const wrongModel = !!suggestModel && suggestionData.run?.model !== suggestModel;
      const requestKey = `${target}:${suggestModel || "default"}`;
      if (awaitingModelRef.current && suggestionData.run?.model === awaitingModelRef.current) awaitingModelRef.current = null;
      const stale = wrongModel && (autoSuggest || !!awaitingModelRef.current);
      setSuggestions((Array.isArray(suggestionData.suggestions) ? suggestionData.suggestions : []).filter((item: ContentGroupSuggestion) => !stale || item.status !== "pending"));
      setNewTopics(!stale && !running && Array.isArray(suggestionData.new_topics) ? suggestionData.new_topics : []);
      if (mountedRef.current && autoSuggest && (!suggestionData.run || (wrongModel && !running)) && !requestedRef.current.has(requestKey) && (feedItemId !== undefined || groupData.content_groups?.some((group: ContentGroup) => group.kind === "topic"))) {
        requestedRef.current.add(requestKey);
        pollsRef.current = 0;
        awaitingModelRef.current = suggestModel || null;
        const requestResponse = await fetch(`${apiUrl}/${target}/group-suggestions`, { method: "POST", headers, body: JSON.stringify({ ...(suggestModel ? { model: suggestModel } : {}), ...(templateId ? { template_id: templateId } : {}) }) });
        if (!requestResponse.ok) throw new Error(`group-suggestions: HTTP ${requestResponse.status}`);
        setPendingRun(true); onModelCall?.();
      } else {
        setPendingRun(running || !!awaitingModelRef.current);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać grup"); }
  }, [apiUrl, headers, target, autoSuggest, suggestModel, templateId, onModelCall, feedItemId]);

  React.useEffect(() => { mountedRef.current = true; void load(); return () => { mountedRef.current = false; }; }, [load]);

  // Poll quietly until the queued classification finishes (or give up after a minute).
  React.useEffect(() => {
    if (!pendingRun || pollsRef.current >= SUGGESTION_POLL_MAX) return;
    const timer = window.setTimeout(() => { pollsRef.current += 1; void load(); }, SUGGESTION_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [pendingRun, load, suggestions]);

  // A preview describes one model + prompt version; drop it as soon as either changes.
  React.useEffect(() => { setPromptPreview(null); setPromptCopied(false); }, [suggestModel, templateId]);

  const showPrompt = async () => {
    setError(""); setPreviewLoading(true);
    try {
      const response = await fetch(`${apiUrl}/feed_items/${feedItemId}/group-suggestions/preview`, {
        method: "POST", headers, body: JSON.stringify({ model: suggestModel, ...(templateId ? { template_id: templateId } : {}) }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || data.error || `group-suggestions/preview: HTTP ${response.status}`);
      setPromptPreview(data as PromptPreview);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać podglądu promptu"); }
    finally { setPreviewLoading(false); }
  };

  const copyPrompt = async () => {
    if (!promptPreview) return;
    setError("");
    try { await copyText(promptPreviewText(promptPreview)); setPromptCopied(true); window.setTimeout(() => setPromptCopied(false), 2000); }
    catch { setError("Nie udało się skopiować promptu do schowka"); }
  };

  const suggestAgain = async () => {
    setError("");
    requestedRef.current.add(`${target}:${suggestModel || "default"}`);
    awaitingModelRef.current = suggestModel || null;
    setSuggestions(items => items.filter(item => item.status !== "pending"));
    setNewTopics([]);
    setRunError("");
    pollsRef.current = 0;
    setPendingRun(false);
    try {
      const response = await fetch(`${apiUrl}/${target}/group-suggestions`, {
        method: "POST", headers, body: JSON.stringify({ model: suggestModel, force: true, ...(templateId ? { template_id: templateId } : {}) }),
      });
      if (!response.ok) throw new Error(`group-suggestions: HTTP ${response.status}`);
      onModelCall?.();
      setPendingRun(true);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać podpowiedzi"); }
  };

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

  const acceptNewTopic = async (proposal: NewTopic) => {
    setCreatingTopic(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/content_groups`, { method: "POST", headers, body: JSON.stringify({ name: proposal.name, kind: "topic" }) });
      let group: ContentGroup;
      if (response.status === 409) {
        const refreshed = await fetch(`${apiUrl}/content_groups`, { headers });
        if (!refreshed.ok) throw new Error(`content_groups: HTTP ${refreshed.status}`);
        const data = await refreshed.json();
        const refreshedCatalog: ContentGroup[] = data.content_groups || [];
        setCatalog(refreshedCatalog);
        const existing = refreshedCatalog.find(item => item.kind === "topic" && !item.archived_at && foldName(item.name) === foldName(proposal.name));
        if (!existing) throw new Error("Nie znaleziono istniejącego tematu");
        group = existing;
      } else {
        if (!response.ok) throw new Error(`content_groups: HTTP ${response.status}`);
        group = await response.json();
        setCatalog(items => [...items.filter(item => item.id !== group.id), group]);
      }
      const ids = [...new Set([...topicIds, group.id])];
      const saved = await fetch(`${apiUrl}/${target}/groups`, { method: "PATCH", headers, body: JSON.stringify({ group_ids: [...ids, ...(priorityId === "" ? [] : [priorityId])] }) });
      const data = await saved.json();
      if (!saved.ok) throw new Error(data.message || data.error || "Nie udało się zapisać grup");
      const next: ContentGroup[] = data.groups || data.feed_item?.groups || [];
      setGroups(next);
      setTopicIds(next.filter(item => item.kind === "topic").map(item => item.id));
      setPriorityId(next.find(item => item.kind === "priority")?.id || "");
      setDismissedTopics(names => [...names, proposal.name]);
      onSaved?.(next);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się dodać tematu"); }
    finally { setCreatingTopic(false); }
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
    {suggestModel && <button type="button" disabled={pendingRun} onClick={() => void suggestAgain()}>Podpowiedz ponownie</button>}
    {feedItemId !== undefined && suggestModel && <>{" "}<button type="button" disabled={previewLoading} onClick={() => void showPrompt()}>{previewLoading ? "Ładuję…" : "Podejrzyj prompt"}</button></>}
    {promptPreview && <div role="region" aria-label="Podgląd promptu" style={{ marginTop: 8, border: "1px solid #cbd5e1", padding: 8, fontSize: ".85em" }}>
      <div style={{ color: "#475569" }}>
        model: <strong>{promptPreview.model.replace(/^openrouter\//, "")}</strong> · prompt: <strong>{promptPreview.prompt_version}</strong> ·{" "}
        {promptPreview.structured ? "schemat odpowiedzi idzie osobno (response_format)" : "model bez trybu strukturalnego — schemat jest w treści promptu"}
        {" "}<button type="button" onClick={() => void copyPrompt()}>{promptCopied ? "Skopiowano ✓" : "Kopiuj prompt"}</button>
        {" "}<button type="button" aria-label="Zamknij podgląd promptu" onClick={() => setPromptPreview(null)}>✕</button>
      </div>
      {promptPreview.system_prompt && <>
        <strong>System{promptPreview.system_sent ? "" : " (nie jest wysyłany dla tego modelu)"}</strong>
        <pre style={{ whiteSpace: "pre-wrap", background: "#f1f5f9", padding: 6, maxHeight: 160, overflow: "auto" }}>{promptPreview.system_prompt}</pre>
      </>}
      <strong>Użytkownik</strong>
      <pre style={{ whiteSpace: "pre-wrap", background: "#f1f5f9", padding: 6, maxHeight: 360, overflow: "auto" }}>{promptPreview.prompt}</pre>
      {promptPreview.response_format != null && <details><summary>response_format (schemat JSON)</summary>
        <pre style={{ whiteSpace: "pre-wrap", background: "#f1f5f9", padding: 6, maxHeight: 240, overflow: "auto" }}>{JSON.stringify(promptPreview.response_format, null, 2)}</pre>
      </details>}
    </div>}
    {suggestModel && runModel && <small style={{ display: "block", color: "#64748b" }}>model: {runModel.replace(/^openrouter\//, "")}</small>}
    {suggestModel && runModel && runPrompt && <small style={{ display: "block", color: "#64748b" }} title="Wersja promptu użyta w tym przebiegu">prompt: {runPrompt}</small>}
    {pendingRun && <div style={{ marginTop: 8, fontSize: "0.85em", color: "#64748b" }}>🤖 Szukam kategorii…</div>}
    {runError && !pendingRun && <p role="alert" className="errorText">Propozycja nie powiodła się{runModel ? ` (${runModel.replace(/^openrouter\//, "")})` : ""}: {runError}</p>}
    {feedItemId !== undefined && !pendingRun && runDone && runModel && !groups.some(group => group.kind === "topic") && suggestions.length === 0 && newTopics.length === 0 && <div style={{ marginTop: 8, fontSize: "0.85em", color: "#64748b" }}>🤖 {runModel.replace(/^openrouter\//, "")}: brak pasującego tematu.</div>}
    {suggestions.filter(item => item.status === "pending").map(item => <div key={item.id} style={{ marginTop: 8, border: "1px dashed #64748b", padding: 6 }}><span>Sugestia: {catalog.find(group => group.id === item.group_id)?.name || item.group_id} ({Math.round(item.confidence * 100)}%)</span>{" "}<button type="button" onClick={() => void decide(item.id, "accept")}>Akceptuj</button>{" "}<button type="button" onClick={() => void decide(item.id, "dismiss")}>Odrzuć</button></div>)}
    {feedItemId !== undefined && !pendingRun && newTopics.filter(item => !dismissedTopics.includes(item.name)).map(item => <div key={item.name} style={{ marginTop: 8 }}>
      <span>Nowy temat: {item.name} ({Math.round(item.confidence * 100)}%) — {item.reason}</span>{" "}
      <button type="button" disabled={creatingTopic} onClick={() => void acceptNewTopic(item)}>Utwórz i dodaj</button>{" "}
      <button type="button" onClick={() => setDismissedTopics(names => [...names, item.name])}>Odrzuć</button>
    </div>)}
    {suggestions.filter(item => item.status === "accepted").map(item => <div key={item.id} style={{ marginTop: 8, fontSize: "0.85em", color: "#475569" }}>
      <span>{item.decided_by_user_id ? "👤" : "🤖"} {catalog.find(group => group.id === item.group_id)?.name || item.group_id} — {Math.round(item.confidence * 100)}%{item.reason ? `: ${item.reason}` : ""}</span>{" "}
      <button type="button" onClick={() => void decide(item.id, "revert")}>Cofnij</button>
    </div>)}
    {error && <p role="alert" className="errorText">{error}</p>}
  </section>;
}
