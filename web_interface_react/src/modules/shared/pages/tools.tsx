import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import ToolRelations, { type ToolRelation } from "../components/ToolRelations/toolRelations";
import GithubStatsLine, { type GithubStats } from "../components/GithubStatsLine/githubStatsLine";

type Tool = {
  id: number;
  uuid: string;
  name: string;
  category_tags: string[];
  homepage_url: string | null;
  license: string | null;
  pricing: string | null;
  github_url: string | null;
  wikipedia_url: string | null;
  pricing_url: string | null;
  pricing_type: string | null;
  app_type: string | null;
  purpose?: string | null;
  works_on?: string | null;
  key_points: string[];
  important_commands: string | null;
  migrating_away: boolean;
  migration_note: string | null;
  migration_target: { id: number; name: string | null } | null;
  github: GithubStats | null;
  personal_notes: string | null;
  source_document_id: number | null;
  source_candidate_id: number | null;
  status: string;
  obsidian_note_path: string | null;
  relations: ToolRelation[];
  created_at: string | null;
  updated_at: string | null;
};

type ToolsResponse = { tools?: unknown; filters?: { tag?: string | null } };
type GithubRefreshResult = { refreshed?: number; failed?: number; rate_limited?: boolean; pending?: number };

const pricingTypes: Array<[string, string]> = [
  ["free", "darmowe"], ["freemium", "freemium"], ["paid", "płatne jednorazowo"],
  ["subscription", "subskrypcja"], ["usage_based", "wg zużycia"], ["open_core", "open core"],
];
const pricingTypeLabel = (value: string | null) => pricingTypes.find(([key]) => key === value)?.[1] ?? value;

// Editable detail fields as form strings; key points are one per line.
type DetailsDraft = {
  app_type: string; purpose: string; works_on: string; license: string; homepage_url: string; github_url: string; wikipedia_url: string;
  pricing_type: string; pricing: string; pricing_url: string; key_points: string; important_commands: string;
  migrating_away: boolean; migration_note: string; migration_target_tool_id: string;
};
const draftFromTool = (tool: Tool): DetailsDraft => ({
  app_type: tool.app_type ?? "", purpose: tool.purpose ?? "", works_on: tool.works_on ?? "",
  license: tool.license ?? "", homepage_url: tool.homepage_url ?? "",
  github_url: tool.github_url ?? "", wikipedia_url: tool.wikipedia_url ?? "",
  pricing_type: tool.pricing_type ?? "", pricing: tool.pricing ?? "", pricing_url: tool.pricing_url ?? "",
  key_points: (tool.key_points ?? []).join("\n"), important_commands: tool.important_commands ?? "",
  migrating_away: tool.migrating_away, migration_note: tool.migration_note ?? "",
  migration_target_tool_id: tool.migration_target ? String(tool.migration_target.id) : "",
});
const detailsPayload = (draft: DetailsDraft) => ({
  ...draft, key_points: draft.key_points.split("\n").map(line => line.trim()).filter(Boolean),
  // The target only exists while migrating away; the server clears it otherwise, so send it consistently.
  migration_target_tool_id: draft.migrating_away && draft.migration_target_tool_id ? Number(draft.migration_target_tool_id) : null,
});
const textFields: Array<[keyof DetailsDraft, string]> = [
  ["purpose", "Do czego służy"], ["works_on", "Działa na (system, platforma)"],
  ["app_type", "Typ aplikacji"], ["license", "Licencja"], ["homepage_url", "Strona"], ["github_url", "GitHub"],
  ["wikipedia_url", "Wikipedia"], ["pricing", "Cennik (opis)"], ["pricing_url", "Strona z cennikiem"],
];
const linkStyle = { fontSize: ".85rem" } as const;

export default function Tools() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const focusedId = Number(searchParams.get("tool")) || null;
  const [tools, setTools] = React.useState<Tool[]>([]);
  const [tags, setTags] = React.useState<string[]>([]);
  const [selectedTag, setSelectedTag] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [editingId, setEditingId] = React.useState<number | null>(null);
  const [draft, setDraft] = React.useState("");
  const [savingId, setSavingId] = React.useState<number | null>(null);
  const [detailsId, setDetailsId] = React.useState<number | null>(null);
  const [detailsDraft, setDetailsDraft] = React.useState<DetailsDraft | null>(null);
  const [onlyLeaving, setOnlyLeaving] = React.useState(false);
  const [githubBusy, setGithubBusy] = React.useState(false);
  const [githubMessage, setGithubMessage] = React.useState("");
  const [importMessage, setImportMessage] = React.useState<{ id: number; text: string } | null>(null);
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

  const patchTool = async (tool: Tool, payload: Record<string, unknown>, failure: string) => {
    setSavingId(tool.id); setError("");
    try {
      const response = await fetch(`${apiUrl}/tools/${tool.id}`, {
        method: "PATCH", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({})) as { tool?: Tool; message?: string };
      if (!response.ok || !data.tool) throw new Error(data.message || `${failure} (HTTP ${response.status})`);
      const saved = data.tool;
      // The PATCH answer carries no relations or GitHub numbers; keep the ones already loaded unless the link changed.
      setTools(current => current.map(item => item.id === tool.id
        ? { ...saved, relations: item.relations, github: saved.github_url === item.github_url ? item.github : null }
        : item));
      return true;
    } catch (cause) { setError(cause instanceof Error ? cause.message : failure); return false; }
    finally { setSavingId(null); }
  };

  const saveNote = async (tool: Tool) => {
    if (await patchTool(tool, { personal_notes: draft }, "Nie udało się zapisać notatki")) setEditingId(null);
  };

  const saveDetails = async (tool: Tool) => {
    if (!detailsDraft) return;
    if (await patchTool(tool, detailsPayload(detailsDraft), "Nie udało się zapisać danych narzędzia")) {
      setDetailsId(null); setDetailsDraft(null);
    }
  };

  const importNote = async (tool: Tool) => {
    setSavingId(tool.id); setError(""); setImportMessage(null);
    try {
      const response = await fetch(`${apiUrl}/tools/${tool.id}/import_note`, {
        method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: "{}",
      });
      const data = await response.json().catch(() => ({})) as { tool?: Tool; imported?: string[]; message?: string };
      if (!response.ok || !data.tool) throw new Error(data.message || `Nie udało się wczytać notatki (HTTP ${response.status})`);
      const saved = data.tool;
      setTools(current => current.map(item => item.id === tool.id
        ? { ...saved, relations: item.relations, github: saved.github_url === item.github_url ? item.github : null }
        : item));
      const count = data.imported?.length ?? 0;
      setImportMessage({ id: tool.id, text: count ? `Uzupełniono ${count} pól: ${data.imported?.join(", ")}.` : "Nic nowego w notatce — wszystkie pola już wypełnione." });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się wczytać notatki"); }
    finally { setSavingId(null); }
  };

  const refreshGithub = async () => {
    setGithubBusy(true); setError(""); setGithubMessage("");
    try {
      const response = await fetch(`${apiUrl}/tools/github_stats/refresh`, { method: "POST", headers });
      const data = await response.json().catch(() => ({})) as GithubRefreshResult & Record<string, unknown>;
      if (!response.ok) throw new Error(String(data.message || "Nie udało się pobrać danych z GitHuba"));
      const pending = data.pending ?? 0;
      setGithubMessage(`GitHub: pobrano ${data.refreshed ?? 0}${data.failed ? `, błędy: ${data.failed}` : ""}${data.rate_limited ? ". Limit zapytań GitHuba wyczerpany — spróbuj za godzinę" : pending ? `. Zostało do pobrania: ${pending} — kliknij ponownie` : ". Wszystko aktualne"}.`);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Pobieranie danych z GitHuba nie powiodło się"); }
    finally { setGithubBusy(false); }
  };

  const reviewRelation = async (id: number, status: "confirmed" | "rejected") => {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_relations/${id}`, {
        method: "PATCH", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify({ status }),
      });
      if (!response.ok) throw new Error("Nie udało się zapisać decyzji o powiązaniu");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Akcja nie powiodła się"); }
  };

  const filteredTools = onlyLeaving ? tools.filter(tool => tool.migrating_away) : tools;
  // Single-tool mode (`?tool=<id>`): one card plus previous/next within the currently filtered list.
  const focusedIndex = focusedId === null ? -1 : filteredTools.findIndex(tool => tool.id === focusedId);
  const focusedTool = focusedIndex >= 0 ? filteredTools[focusedIndex] : null;
  const visibleTools = focusedId === null ? filteredTools : focusedTool ? [focusedTool] : [];
  const previousTool = focusedIndex > 0 ? filteredTools[focusedIndex - 1] : null;
  const nextTool = focusedIndex >= 0 && focusedIndex < filteredTools.length - 1 ? filteredTools[focusedIndex + 1] : null;

  const focusTool = React.useCallback((id: number | null) => {
    setSearchParams(current => {
      const next = new URLSearchParams(current);
      if (id === null) next.delete("tool"); else next.set("tool", String(id));
      return next;
    });
    window.scrollTo({ top: 0 });
  }, [setSearchParams]);

  React.useEffect(() => {
    if (focusedId === null) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.key === "ArrowLeft" && previousTool) focusTool(previousTool.id);
      if (event.key === "ArrowRight" && nextTool) focusTool(nextTool.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusedId, previousTool, nextTool, focusTool]);

  const formatDate =(value: string | null) => value ? new Date(value).toLocaleString("pl-PL") : null;

  return <section style={{ maxWidth: 1100, padding: "28px 24px" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h1 style={{ color: "#0c2f4a", margin: 0 }}>Spis narzędzi</h1>
        <span
          title={"Spis narzędzi, które świadomie wybrałeś (etap „Używam” w Radarze narzędzi trafia tu automatycznie).\n\n" +
            "Notatkę o narzędziu piszesz i edytujesz tutaj, w Lenie — Obsidian nie jest potrzebny. " +
            "Starsze narzędzia mogą mieć dodatkowo notatkę w Obsidianie (pokazana jako starsza kopia).\n\n" +
            "Powiązania (współpracuje z, alternatywa dla…) pochodzą z Radaru narzędzi; propozycje potwierdzasz ✓ lub odrzucasz ✗."}
          style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 20, height: 20, borderRadius: "50%", background: "#e2e8f0", color: "#334155",
            fontSize: "0.75rem", fontWeight: 700, cursor: "help",
          }}
        >
          ?
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => void refreshGithub()} disabled={githubBusy || loading} title="Pobiera gwiazdki, forki i aktywność z publicznego API GitHuba dla narzędzi z linkiem do repozytorium (do 30 na raz). Dane są wspólne z Radarem narzędzi.">{githubBusy ? "Pobieram z GitHuba…" : "Odśwież dane GitHuba"}</button>
        <button className="button" type="button" onClick={() => void load()} disabled={loading}>Odśwież</button>
      </div>
    </div>
    {githubMessage && <p role="status" style={{ color: "#166534", margin: "8px 0 0" }}>{githubMessage}</p>}
    <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap", margin: "8px 0 20px" }}>
      <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
        Tag:
        <select value={selectedTag} onChange={event => setSelectedTag(event.target.value)} disabled={loading && tags.length === 0}>
          <option value="">Wszystkie tagi</option>
          {tags.map(tag => <option key={tag} value={tag}>{tag}</option>)}
        </select>
      </label>
      <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }} title="Narzędzia oznaczone jako te, z których wychodzę (np. Obsidian).">
        <input type="checkbox" checked={onlyLeaving} onChange={event => setOnlyLeaving(event.target.checked)} />
        Tylko te, z których odchodzę
      </label>
    </div>
    {error && <p className="errorText" role="alert">{error}</p>}
    {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
    {focusedId !== null && <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", margin: "0 0 14px" }}>
      <button type="button" onClick={() => focusTool(null)}>← Wszystkie narzędzia</button>
      <button type="button" disabled={!previousTool} onClick={() => previousTool && focusTool(previousTool.id)}
        title={previousTool ? `Poprzednie: ${previousTool.name} (strzałka w lewo)` : "To pierwsze narzędzie"}>← Poprzednie</button>
      {focusedTool && <span style={{ color: "#64748b", fontSize: ".85rem" }}>{focusedIndex + 1} / {filteredTools.length}</span>}
      <button type="button" disabled={!nextTool} onClick={() => nextTool && focusTool(nextTool.id)}
        title={nextTool ? `Następne: ${nextTool.name} (strzałka w prawo)` : "To ostatnie narzędzie"}>Następne →</button>
    </div>}
    {!loading && !error && focusedId !== null && !focusedTool && <p>Nie znaleziono narzędzia #{focusedId} na bieżącej liście (sprawdź filtry tagu).</p>}
    {!loading && !error && focusedId === null && !visibleTools.length && <p>{onlyLeaving ? "Żadne narzędzie nie jest oznaczone jako „odchodzę”." : selectedTag ? "Brak zapisanych narzędzi dla wybranego tagu." : "Brak zapisanych narzędzi."}</p>}
    {visibleTools.map(tool => <article key={tool.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
      <h3>{focusedId === null
        ? <Link to={`/tools?tool=${tool.id}`} title="Pokaż to narzędzie osobno" style={{ color: "inherit" }}>{tool.name}</Link>
        : tool.name}
        {tool.migrating_away && <span title={tool.migration_note || "Wychodzę z tego narzędzia"} style={{ marginLeft: 8, background: "#fef3c7", color: "#92400e", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem", fontWeight: 400 }}>odchodzę</span>}
      </h3>
      {tool.migrating_away && (tool.migration_target || tool.migration_note) && <div style={{ color: "#92400e", fontSize: ".85rem", margin: "4px 0" }}>
        {tool.migration_target && <span>Przechodzę na: <Link to={`/tools?tool=${tool.migration_target.id}`}>{tool.migration_target.name ?? `#${tool.migration_target.id}`}</Link></span>}
        {tool.migration_target && tool.migration_note && <span> · </span>}
        {tool.migration_note}
      </div>}
      {tool.category_tags.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "8px 0" }}>
        {tool.category_tags.map(tag => <span key={tag} style={{ background: "#e2e8f0", color: "#334155", borderRadius: 4, padding: "2px 6px", fontSize: ".75rem" }}>{tag}</span>)}
      </div>}
      {tool.purpose && <blockquote style={{ margin: "8px 0", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 12 }}>{tool.purpose}</blockquote>}
      {(tool.app_type || tool.works_on) && <div style={{ color: "#64748b", fontSize: ".85rem" }}>
        {tool.app_type && <span>Typ: {tool.app_type}</span>}
        {tool.app_type && tool.works_on && <span> · </span>}
        {tool.works_on && <span>Działa na: {tool.works_on}</span>}
      </div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, margin: "4px 0" }}>
        {tool.homepage_url && <a style={linkStyle} href={tool.homepage_url} target="_blank" rel="noreferrer">Strona</a>}
        {tool.github_url && <a style={linkStyle} href={tool.github_url} target="_blank" rel="noreferrer">GitHub</a>}
        {tool.wikipedia_url && <a style={linkStyle} href={tool.wikipedia_url} target="_blank" rel="noreferrer">Wikipedia</a>}
        {tool.pricing_url && <a style={linkStyle} href={tool.pricing_url} target="_blank" rel="noreferrer">Cennik</a>}
      </div>
      {tool.github && <GithubStatsLine stats={tool.github} />}
      {focusedId !== null && <div style={{ background: "#f8fafc", borderRadius: 8, padding: "8px 12px", margin: "8px 0", fontSize: ".85rem", color: "#475569" }}>
        <strong>Linki i źródła</strong>
        <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
          {tool.homepage_url && <li>Strona: <a href={tool.homepage_url} target="_blank" rel="noreferrer">{tool.homepage_url}</a></li>}
          {tool.github_url && <li>Repozytorium GitHub: <a href={tool.github_url} target="_blank" rel="noreferrer">{tool.github_url}</a></li>}
          {tool.wikipedia_url && <li>Wikipedia: <a href={tool.wikipedia_url} target="_blank" rel="noreferrer">{tool.wikipedia_url}</a></li>}
          {tool.pricing_url && <li>Cennik: <a href={tool.pricing_url} target="_blank" rel="noreferrer">{tool.pricing_url}</a></li>}
          {tool.source_document_id && <li>Dokument źródłowy w Lenie: <Link to={`/read/${tool.source_document_id}`}>#{tool.source_document_id}</Link></li>}
          {tool.source_candidate_id && <li>Kandydat, z którego powstało: #{tool.source_candidate_id}</li>}
          {!tool.homepage_url && !tool.github_url && !tool.wikipedia_url && !tool.pricing_url && !tool.source_document_id && <li>Brak zapisanych linków — użyj „Edytuj dane”.</li>}
        </ul>
      </div>}
      {(tool.license || tool.pricing || tool.pricing_type) && <div style={{ color: "#64748b", fontSize: ".85rem", margin: "8px 0" }}>
        {tool.license && <span>Licencja: {tool.license}</span>}
        {tool.license && (tool.pricing_type || tool.pricing) && <span> · </span>}
        {tool.pricing_type && <span>Model: {pricingTypeLabel(tool.pricing_type)}</span>}
        {tool.pricing_type && tool.pricing && <span> · </span>}
        {tool.pricing && <span>Cennik: {tool.pricing}</span>}
      </div>}
      {tool.key_points.length > 0 && <ul style={{ margin: "8px 0", paddingLeft: 20, color: "#334155" }}>
        {tool.key_points.map(point => <li key={point}>{point}</li>)}
      </ul>}
      {tool.important_commands && <details style={{ margin: "8px 0" }}>
        <summary style={{ cursor: "pointer", color: "#475569", fontSize: ".85rem" }}>Ważne polecenia</summary>
        <pre style={{ background: "#f1f5f9", borderRadius: 6, padding: 10, overflowX: "auto", margin: "6px 0 0" }}>{tool.important_commands}</pre>
      </details>}
      {detailsId === tool.id && detailsDraft ? <div style={{ border: "1px dashed #cbd5e1", borderRadius: 8, padding: 12, margin: "8px 0" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 10 }}>
          {textFields.map(([field, label]) => <label key={field} style={{ display: "flex", flexDirection: "column", fontSize: ".85rem", color: "#475569" }}>
            {label}
            <input value={detailsDraft[field] as string} disabled={savingId === tool.id}
              onChange={event => setDetailsDraft({ ...detailsDraft, [field]: event.target.value })} />
          </label>)}
          <label style={{ display: "flex", flexDirection: "column", fontSize: ".85rem", color: "#475569" }}>
            Model cenowy
            <select value={detailsDraft.pricing_type} disabled={savingId === tool.id}
              onChange={event => setDetailsDraft({ ...detailsDraft, pricing_type: event.target.value })}>
              <option value="">—</option>
              {pricingTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
        </div>
        <label style={{ display: "flex", flexDirection: "column", fontSize: ".85rem", color: "#475569", marginTop: 10 }}>
          Najważniejsze punkty (jeden w wierszu)
          <textarea rows={4} value={detailsDraft.key_points} disabled={savingId === tool.id}
            onChange={event => setDetailsDraft({ ...detailsDraft, key_points: event.target.value })} />
        </label>
        <label style={{ display: "flex", flexDirection: "column", fontSize: ".85rem", color: "#475569", marginTop: 10 }}>
          Ważne polecenia
          <textarea rows={4} value={detailsDraft.important_commands} disabled={savingId === tool.id} style={{ fontFamily: "monospace" }}
            onChange={event => setDetailsDraft({ ...detailsDraft, important_commands: event.target.value })} />
        </label>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 10 }}>
          <input type="checkbox" checked={detailsDraft.migrating_away} disabled={savingId === tool.id}
            onChange={event => setDetailsDraft({ ...detailsDraft, migrating_away: event.target.checked })} />
          Odchodzę od tego narzędzia
        </label>
        {detailsDraft.migrating_away && <>
          <label style={{ display: "flex", flexDirection: "column", fontSize: ".85rem", color: "#475569", marginTop: 6 }}>
            Na jakie narzędzie przechodzę
            <select value={detailsDraft.migration_target_tool_id} disabled={savingId === tool.id}
              onChange={event => setDetailsDraft({ ...detailsDraft, migration_target_tool_id: event.target.value })}>
              <option value="">— jeszcze nie wybrane / spoza spisu —</option>
              {tool.migration_target && !tools.some(other => other.id === tool.migration_target?.id)
                && <option value={tool.migration_target.id}>{tool.migration_target.name}</option>}
              {tools.filter(other => other.id !== tool.id).map(other => <option key={other.id} value={other.id}>{other.name}</option>)}
            </select>
          </label>
          <label style={{ display: "flex", flexDirection: "column", fontSize: ".85rem", color: "#475569", marginTop: 6 }}>
            Dlaczego / uwagi (np. narzędzie spoza spisu)
            <input value={detailsDraft.migration_note} disabled={savingId === tool.id}
              onChange={event => setDetailsDraft({ ...detailsDraft, migration_note: event.target.value })} />
          </label>
        </>}
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <button className="button" type="button" disabled={savingId === tool.id} onClick={() => void saveDetails(tool)}>Zapisz dane</button>
          <button type="button" disabled={savingId === tool.id} onClick={() => { setDetailsId(null); setDetailsDraft(null); }}>Anuluj</button>
        </div>
      </div> : <div style={{ margin: "8px 0" }}>
        <button type="button" onClick={() => { setDetailsId(tool.id); setDetailsDraft(draftFromTool(tool)); }}>Edytuj dane</button>
        {tool.obsidian_note_path && <button type="button" style={{ marginLeft: 8 }} disabled={savingId === tool.id}
          title="Czyta notatkę z vaulta Obsidian (szablon opisu aplikacji) i uzupełnia tylko puste pola: do czego służy, system, licencję, linki, cennik, punkty i polecenia."
          onClick={() => void importNote(tool)}>Wczytaj z notatki</button>}
        {importMessage?.id === tool.id && <span role="status" style={{ marginLeft: 10, color: "#166534", fontSize: ".85rem" }}>{importMessage.text}</span>}
      </div>}
      <ToolRelations relations={tool.relations ?? []} onReview={(id, status) => void reviewRelation(id, status)} />
      {editingId === tool.id ? <div style={{ margin: "8px 0" }}>
        <textarea aria-label={`Notatka o ${tool.name}`} value={draft} onChange={event => setDraft(event.target.value)} rows={8}
          style={{ width: "100%", boxSizing: "border-box" }} disabled={savingId === tool.id} />
        <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
          <button className="button" type="button" disabled={savingId === tool.id} onClick={() => void saveNote(tool)}>Zapisz notatkę</button>
          <button type="button" disabled={savingId === tool.id} onClick={() => setEditingId(null)}>Anuluj</button>
        </div>
      </div> : <div style={{ margin: "8px 0" }}>
        {tool.personal_notes
          ? <blockquote style={{ margin: "0 0 6px", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 12, whiteSpace: "pre-wrap" }}>{tool.personal_notes}</blockquote>
          : <div style={{ color: "#64748b", fontSize: ".85rem", marginBottom: 6 }}>Brak notatki — napisz, do czego używasz tego narzędzia.</div>}
        <button type="button" onClick={() => { setEditingId(tool.id); setDraft(tool.personal_notes ?? ""); }}>{tool.personal_notes ? "Edytuj notatkę" : "Dodaj notatkę"}</button>
      </div>}
      {tool.obsidian_note_path && <div style={{ color: "#64748b", fontSize: ".85rem", marginTop: 8 }}>
        Starsza kopia w Obsidianie: {tool.obsidian_note_path}
      </div>}
      {formatDate(tool.created_at) && <div style={{ color: "#64748b", fontSize: ".85rem", marginTop: 6 }}>Dodano: {formatDate(tool.created_at)}</div>}
    </article>)}
  </section>;
}
