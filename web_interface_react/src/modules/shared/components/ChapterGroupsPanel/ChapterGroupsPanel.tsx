import React from "react";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";
import type { ContentGroup } from "../../../../types";

type Props = { documentId: string; position: number };

export default function ChapterGroupsPanel({ documentId, position }: Props) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "", "Content-Type": "application/json" }), [apiKey]);
  const [catalog, setCatalog] = React.useState<ContentGroup[]>([]);
  const [groups, setGroups] = React.useState<ContentGroup[]>([]);
  const [supported, setSupported] = React.useState(true);
  const [editing, setEditing] = React.useState(false);
  const [selected, setSelected] = React.useState<number[]>([]);
  const [newName, setNewName] = React.useState("");
  const [error, setError] = React.useState("");
  const base = `${apiUrl}/document/${documentId}/chapter/${position}/groups`;

  const load = React.useCallback(async () => {
    setError("");
    try {
      const currentResponse = await fetch(base, { headers });
      if (currentResponse.status === 409) { setSupported(false); return; }
      const currentData = await currentResponse.json();
      if (!currentResponse.ok) throw new Error(currentData.message || "Nie udało się pobrać kategorii");
      const catalogResponse = await fetch(`${apiUrl}/content_groups`, { headers });
      const catalogData = await catalogResponse.json();
      const current = Array.isArray(currentData.groups) ? currentData.groups : [];
      setSupported(true); setGroups(current); setSelected(current.map((group: ContentGroup) => group.id));
      setCatalog(Array.isArray(catalogData.content_groups) ? catalogData.content_groups : []);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać kategorii"); }
  }, [apiUrl, base, headers]);

  React.useEffect(() => { void load(); }, [load]);
  const save = async (nextIds = selected) => {
    setError("");
    const response = await fetch(base, { method: "PATCH", headers, body: JSON.stringify({ group_ids: nextIds }) });
    const data = await response.json();
    if (!response.ok) { setError(data.message || "Nie udało się zapisać kategorii"); return; }
    const next = Array.isArray(data.groups) ? data.groups : [];
    setGroups(next); setSelected(next.map((group: ContentGroup) => group.id)); setEditing(false);
  };
  const create = async () => {
    const name = newName.trim(); if (!name) return;
    const response = await fetch(`${apiUrl}/content_groups`, { method: "POST", headers, body: JSON.stringify({ name, kind: "topic" }) });
    const data = await response.json();
    if (!response.ok) { setError(data.message || data.error || "Nie udało się utworzyć kategorii"); return; }
    setCatalog(items => [...items, data].sort((a, b) => a.name.localeCompare(b.name, "pl"))); setNewName("");
    await save([...selected, data.id]);
  };

  if (!supported) return null;
  const topics = catalog.filter(group => group.kind === "topic");
  return <section aria-label="Kategorie rozdziału" style={{ border: "1px solid #dbe4ee", borderRadius: 8, padding: 10, marginBottom: 14 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
      <strong>📌 Kategorie tego fragmentu</strong>
      {groups.map(group => <NavLink key={group.id} to={`/chapter-groups?group_id=${group.id}`} style={{ background: "#f1f5f9", borderRadius: 12, padding: "2px 8px", color: "#0369a1" }}>{group.name}</NavLink>)}
      {!groups.length && <span style={{ color: "#64748b" }}>Brak</span>}
      <button type="button" onClick={() => setEditing(value => !value)}>{editing ? "Anuluj" : "Edytuj"}</button>
    </div>
    {editing && <div style={{ marginTop: 8 }}>
      {topics.map(group => <label key={group.id} style={{ display: "inline-block", marginRight: 10 }}><input type="checkbox" checked={selected.includes(group.id)} onChange={event => setSelected(ids => event.target.checked ? [...ids, group.id] : ids.filter(id => id !== group.id))} /> {group.name}</label>)}
      <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
        <input value={newName} maxLength={80} onChange={event => setNewName(event.target.value)} placeholder="Nowa kategoria, np. Ciekawe narzędzia" />
        <button type="button" onClick={() => void create()}>Dodaj kategorię</button><button type="button" className="button" onClick={() => void save()}>Zapisz</button>
      </div>
    </div>}
    {error && <p role="alert" className="errorText">{error}</p>}
  </section>;
}
