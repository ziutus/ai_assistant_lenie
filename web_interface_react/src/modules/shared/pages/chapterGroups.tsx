import React from "react";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import type { ContentGroup } from "../../../types";

type Entry = { document_id: number; chapter_position: number | null; title: string; document_title: string | null; summary: string | null };

export default function ChapterGroups() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [params, setParams] = useSearchParams();
  const [groups, setGroups] = React.useState<ContentGroup[]>([]);
  const [entries, setEntries] = React.useState<Entry[]>([]);
  const [error, setError] = React.useState("");
  const groupId = Number(params.get("group_id")) || undefined;
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "" }), [apiKey]);
  React.useEffect(() => { void fetch(`${apiUrl}/content_groups`, { headers }).then(response => response.json()).then(data => setGroups((Array.isArray(data.content_groups) ? data.content_groups : []).filter((group: ContentGroup) => group.kind === "topic"))).catch(() => setError("Nie udało się pobrać kategorii")); }, [apiUrl, headers]);
  React.useEffect(() => { if (!groupId) { setEntries([]); return; } void fetch(`${apiUrl}/chapter_group_entries?group_id=${groupId}`, { headers }).then(async response => { const data = await response.json(); if (!response.ok) throw new Error(data.message || "Nie udało się pobrać fragmentów"); setEntries(Array.isArray(data.entries) ? data.entries : []); }).catch(cause => setError(cause instanceof Error ? cause.message : "Nie udało się pobrać fragmentów")); }, [apiUrl, groupId, headers]);
  return <div><h2>Kategorie fragmentów</h2><label>Kategoria <select value={groupId || ""} onChange={event => setParams(event.target.value ? { group_id: event.target.value } : {})}><option value="">Wybierz kategorię</option>{groups.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>{groupId && <p style={{ color: "#64748b" }}>{entries.length} zapisanych fragmentów</p>}{entries.map(entry => <article key={`${entry.document_id}:${entry.chapter_position}`} style={{ borderBottom: "1px solid #e2e8f0", padding: "10px 0" }}><NavLink to={`/read/${entry.document_id}?chapter=${entry.chapter_position ?? 1}`} style={{ color: "#0369a1", fontWeight: 600 }}>{entry.title}</NavLink>{entry.document_title && <div style={{ fontSize: "0.85em", color: "#64748b" }}>{entry.document_title}</div>}{entry.summary && <p style={{ margin: "5px 0 0" }}>{entry.summary}</p>}</article>)}{error && <p role="alert" className="errorText">{error}</p>}</div>;
}
