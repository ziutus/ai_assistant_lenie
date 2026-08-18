import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

type Tool = {
  id: number;
  uuid: string;
  name: string;
  category_tags: string[];
  homepage_url: string | null;
  license: string | null;
  pricing: string | null;
  personal_notes: string | null;
  source_document_id: number | null;
  source_candidate_id: number | null;
  status: string;
  obsidian_note_path: string | null;
  created_at: string | null;
  updated_at: string | null;
};

type ToolsResponse = { tools?: unknown; filters?: { tag?: string | null } };

export default function Tools() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [tools, setTools] = React.useState<Tool[]>([]);
  const [tags, setTags] = React.useState<string[]>([]);
  const [selectedTag, setSelectedTag] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const headers = React.useMemo(() => ({ "x-api-key": apiKey || "" }), [apiKey]);
  // Guards against out-of-order responses: switching the tag filter quickly
  // aborts the previous in-flight request so a slower, stale response for an
  // earlier tag can never overwrite the results of a newer selection.
  const abortRef = React.useRef<AbortController | null>(null);

  const load = React.useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (selectedTag) params.set("tag", selectedTag);
      const query = params.toString();
      const response = await fetch(`${apiUrl}/tools${query ? `?${query}` : ""}`, { headers, signal: controller.signal });
      const readResponse = async (result: Response): Promise<Record<string, unknown>> => {
        const text = await result.text();
        if (!text) return {};
        try { return JSON.parse(text) as Record<string, unknown>; } catch { return { message: text }; }
      };
      const data = await readResponse(response) as ToolsResponse & Record<string, unknown>;
      if (!response.ok) {
        const detail = response.status === 401 || response.status === 403
          ? "Klucz API nie ma uprawnień do przeglądu spisu narzędzi"
          : String(data.message || "Nie udało się pobrać spisu narzędzi");
        throw new Error(`${detail} (HTTP ${response.status}, ${apiUrl}/tools)`);
      }
      const loadedTools = Array.isArray(data.tools) ? data.tools as Tool[] : [];
      setTools(loadedTools);
      setTags(currentTags => Array.from(new Set([
        ...currentTags,
        ...loadedTools.flatMap(tool => tool.category_tags),
      ])).sort((tagA, tagB) => tagA.localeCompare(tagB, "pl")));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof TypeError
        ? `Nie można połączyć się z API ${apiUrl}. Sprawdź adres API, CORS i połączenie z NAS-em.`
        : cause instanceof Error ? cause.message : "Nie udało się pobrać spisu narzędzi");
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  }, [apiUrl, headers, selectedTag]);

  React.useEffect(() => { void load(); }, [load]);

  const formatDate = (value: string | null) => value ? new Date(value).toLocaleString("pl-PL") : null;

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <h1 style={{ color: "#0c2f4a" }}>Spis narzędzi</h1>
      <button className="button" type="button" onClick={() => void load()} disabled={loading}>Odśwież</button>
    </div>
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, margin: "8px 0 20px" }}>
      Tag:
      <select value={selectedTag} onChange={event => setSelectedTag(event.target.value)} disabled={loading && tags.length === 0}>
        <option value="">Wszystkie tagi</option>
        {tags.map(tag => <option key={tag} value={tag}>{tag}</option>)}
      </select>
    </label>
    {error && <p className="errorText" role="alert">{error}</p>}
    {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
    {!loading && !error && !tools.length && <p>{selectedTag ? "Brak zapisanych narzędzi dla wybranego tagu." : "Brak zapisanych narzędzi."}</p>}
    {tools.map(tool => <article key={tool.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
      <h3>{tool.name}</h3>
      {tool.category_tags.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "8px 0" }}>
        {tool.category_tags.map(tag => <span key={tag} style={{ background: "#e2e8f0", color: "#334155", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>{tag}</span>)}
      </div>}
      {tool.homepage_url && <div><a href={tool.homepage_url} target="_blank" rel="noreferrer">{tool.homepage_url}</a></div>}
      {(tool.license || tool.pricing) && <div style={{ color: "#64748b", fontSize: ".85rem", margin: "8px 0" }}>
        {tool.license && <span>Licencja: {tool.license}</span>}
        {tool.license && tool.pricing && <span> · </span>}
        {tool.pricing && <span>Cennik: {tool.pricing}</span>}
      </div>}
      {tool.personal_notes && <blockquote style={{ margin: "8px 0", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 12 }}>
        {tool.personal_notes}
      </blockquote>}
      <div style={{ color: tool.obsidian_note_path ? "#166534" : "#b45309", fontSize: ".85rem", marginTop: 8 }}>
        {tool.obsidian_note_path ? `✓ Notatka w Obsidian: ${tool.obsidian_note_path}` : "⚠ brak notatki w Obsidian"}
      </div>
      {formatDate(tool.created_at) && <div style={{ color: "#64748b", fontSize: ".85rem", marginTop: 6 }}>Dodano: {formatDate(tool.created_at)}</div>}
    </article>)}
  </section>;
}
