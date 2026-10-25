import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import ToolRelations, { type ToolRelation } from "../components/ToolRelations/toolRelations";
import GithubStatsLine, { type GithubStats } from "../components/GithubStatsLine/githubStatsLine";
import MarkdownView from "../components/MarkdownView/markdownView";
import MarkdownEditor from "../components/MarkdownView/markdownEditor";
import {
  Chip, DocumentLink, Section, ToolFacts, ToolLinks, linksToText, shortDate, textToLinks, toolLinks,
} from "../components/ToolCard/toolCardParts";

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
  links?: Array<{ url: string; label: string }>;
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
  sources?: ToolSourceLink[];
  radar?: RadarOrigin[];
  created_at: string | null;
  updated_at: string | null;
};

// Where the user learned about the tool (a course, a newsletter...) - knowledge sources linked through /tools/:id/sources.
type ToolSourceLink = {
  id: number; name: string; kind: string | null; url: string | null; status: string | null; rating: number | null;
  context: string | null;
};
type KnownSource = { id: number; name: string; is_active: boolean };
type DocumentRef = { id: number; title: string | null; url: string | null; discovery_source: string | null };
// Why the tool was on the radar: the linked radar entry's own provenance (read through tool_recommendations.tool_id).
type RadarOrigin = {
  id: number; status: string; source_context: string | null; source_url: string | null; created_at: string | null;
  source_document: DocumentRef | null; evidence_count: number;
  evidences: Array<{
    relation_type: string; catalog_label: string | null; catalog_url: string | null; context: string | null;
    recommender_document: DocumentRef | null;
  }>;
};
const radarStatusLabel: Record<string, string> = {
  watchlist: "Obserwuję", compare: "Porównuję", testing: "Testuję", adopted: "Używam", test_future: "Przetestuję w przyszłości", phasing_out: "Wygaszam", rejected: "Odrzuciłem", archived: "Archiwum",
};

type ToolsResponse = { tools?: unknown; filters?: { tag?: string | null } };
type GithubRefreshResult = { refreshed?: number; failed?: number; rate_limited?: boolean; quota_reserved?: boolean; rate_limit_remaining?: number | null; pending?: number };

const pricingTypes: Array<[string, string]> = [
  ["free", "darmowe"], ["freemium", "freemium"], ["paid", "płatne jednorazowo"],
  ["subscription", "subskrypcja"], ["usage_based", "wg zużycia"], ["open_core", "open core"],
];
const pricingTypeLabel = (value: string | null) => pricingTypes.find(([key]) => key === value)?.[1] ?? value;

// Editable detail fields as form strings; key points are one per line.
type DetailsDraft = {
  app_type: string; purpose: string; works_on: string; license: string; homepage_url: string; github_url: string; wikipedia_url: string;
  pricing_type: string; pricing: string; pricing_url: string;
  links: string; // one per line: "https://…" or "Label | https://…"
  migrating_away: boolean; migration_note: string; migration_target_tool_id: string;
};
const draftFromTool = (tool: Tool): DetailsDraft => ({
  app_type: tool.app_type ?? "", purpose: tool.purpose ?? "", works_on: tool.works_on ?? "",
  license: tool.license ?? "", homepage_url: tool.homepage_url ?? "",
  github_url: tool.github_url ?? "", wikipedia_url: tool.wikipedia_url ?? "",
  pricing_type: tool.pricing_type ?? "", pricing: tool.pricing ?? "", pricing_url: tool.pricing_url ?? "",
  links: linksToText(tool.links),
  migrating_away: tool.migrating_away, migration_note: tool.migration_note ?? "",
  migration_target_tool_id: tool.migration_target ? String(tool.migration_target.id) : "",
});
const detailsPayload = (draft: DetailsDraft) => ({
  ...draft,
  links: textToLinks(draft.links),
  // The target only exists while migrating away; the server clears it otherwise, so send it consistently.
  migration_target_tool_id: draft.migrating_away && draft.migration_target_tool_id ? Number(draft.migration_target_tool_id) : null,
});
const textFields: Array<[keyof DetailsDraft, string]> = [
  ["purpose", "Do czego służy"], ["works_on", "Działa na (system, platforma)"],
  ["app_type", "Typ aplikacji"], ["license", "Licencja"], ["homepage_url", "Strona"], ["github_url", "GitHub"],
  ["wikipedia_url", "Wikipedia"], ["pricing", "Cennik (opis)"], ["pricing_url", "Strona z cennikiem"],
];

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
  const [knownSources, setKnownSources] = React.useState<KnownSource[]>([]);
  const [sourceToolId, setSourceToolId] = React.useState<number | null>(null);
  const [sourceDraft, setSourceDraft] = React.useState("");
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
        ? { ...saved, relations: item.relations, sources: item.sources, radar: item.radar, github: saved.github_url === item.github_url ? item.github : null }
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

  // The picker offers the existing sources (fetched on first use); a new name is created on the fly by the server.
  const openSourcePicker = (tool: Tool) => {
    setSourceToolId(tool.id); setSourceDraft("");
    if (knownSources.length) return;
    fetch(`${apiUrl}/sources?active=1`, { headers })
      .then(response => response.ok ? response.json() : { sources: [] })
      .then((data: { sources?: KnownSource[] }) => setKnownSources(data.sources ?? []))
      .catch(() => { /* the picker just stays empty */ });
  };

  const setToolSources = (toolId: number, sources: ToolSourceLink[]) =>
    setTools(current => current.map(item => item.id === toolId ? { ...item, sources } : item));

  const addSource = async (tool: Tool) => {
    const name = sourceDraft.trim();
    if (!name) return;
    setSavingId(tool.id); setError("");
    try {
      const known = knownSources.find(source => source.name.toLowerCase() === name.toLowerCase());
      const response = await fetch(`${apiUrl}/tools/${tool.id}/sources`, {
        method: "POST", headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(known ? { source_id: known.id } : { name }),
      });
      const data = await response.json().catch(() => ({})) as { sources?: ToolSourceLink[]; source_created?: boolean; message?: string };
      if (!response.ok || !data.sources) throw new Error(data.message || `Nie udało się dodać źródła (HTTP ${response.status})`);
      setToolSources(tool.id, data.sources);
      if (data.source_created) setKnownSources(current => [...current, { id: -1, name, is_active: true }]);
      setSourceDraft(""); setSourceToolId(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się dodać źródła"); }
    finally { setSavingId(null); }
  };

  const removeSource = async (tool: Tool, source: ToolSourceLink) => {
    setSavingId(tool.id); setError("");
    try {
      const response = await fetch(`${apiUrl}/tools/${tool.id}/sources/${source.id}`, { method: "DELETE", headers });
      const data = await response.json().catch(() => ({})) as { sources?: ToolSourceLink[]; message?: string };
      if (!response.ok || !data.sources) throw new Error(data.message || `Nie udało się usunąć źródła (HTTP ${response.status})`);
      setToolSources(tool.id, data.sources);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się usunąć źródła"); }
    finally { setSavingId(null); }
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
        ? { ...saved, relations: item.relations, radar: item.radar, github: saved.github_url === item.github_url ? item.github : null }
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
      setGithubMessage(`GitHub: pobrano ${data.refreshed ?? 0}${data.failed ? `, błędy: ${data.failed}` : ""}${data.quota_reserved ? `. Pobieranie wstrzymane, aby zachować rezerwę godzinnego limitu GitHuba. Pozostałe repozytoria (${pending}) można pobrać później` : data.rate_limited ? ". Limit zapytań GitHuba wyczerpany — spróbuj za godzinę" : pending ? `. Zostało do pobrania: ${pending} — kliknij ponownie` : ". Wszystko aktualne"}.${data.rate_limit_remaining != null ? ` Pozostały limit GitHuba: ${data.rate_limit_remaining} zapytań.` : ""}`);
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
        <button type="button" onClick={() => void refreshGithub()} disabled={githubBusy || loading} title="Pobiera gwiazdki, forki i aktywność z publicznego API GitHuba dla narzędzi z linkiem do repozytorium (do kilkuset repozytoriów na raz, zależnie od limitu GitHuba). Dane są wspólne z Radarem narzędzi.">{githubBusy ? "Pobieram z GitHuba…" : "Odśwież dane GitHuba"}</button>
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
    {visibleTools.map(tool => {
      const links = toolLinks(tool);
      const sources = tool.sources ?? [];
      const radar = tool.radar ?? [];
      return <article key={tool.id} style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "16px 18px", marginBottom: 14 }}>
        <header style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>{focusedId === null
            ? <Link to={`/tools?tool=${tool.id}`} title="Pokaż to narzędzie osobno" style={{ color: "inherit" }}>{tool.name}</Link>
            : tool.name}
            {tool.migrating_away && <span title={tool.migration_note || "Wychodzę z tego narzędzia"} style={{ marginLeft: 8, fontWeight: 400 }}><Chip tone="warn">odchodzę</Chip></span>}
          </h3>
          {tool.github && <GithubStatsLine stats={tool.github} />}
        </header>
        {tool.category_tags.length > 0 && <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "8px 0 0" }}>
          {tool.category_tags.map(tag => <Chip key={tag}>{tag}</Chip>)}
        </div>}
        {tool.migrating_away && (tool.migration_target || tool.migration_note) && <div style={{ color: "#92400e", fontSize: ".85rem", margin: "8px 0 0" }}>
          {tool.migration_target && <span>Przechodzę na: <Link to={`/tools?tool=${tool.migration_target.id}`}>{tool.migration_target.name ?? `#${tool.migration_target.id}`}</Link></span>}
          {tool.migration_target && tool.migration_note && <span> · </span>}
          {tool.migration_note}
        </div>}
        {tool.purpose && <p style={{ margin: "12px 0 0", color: "#334155", fontSize: "1rem", whiteSpace: "pre-wrap" }}>{tool.purpose}</p>}
        <ToolFacts facts={[
          ["Typ", tool.app_type], ["Działa na", tool.works_on], ["Licencja", tool.license],
          ["Model cenowy", pricingTypeLabel(tool.pricing_type)], ["Cennik", tool.pricing],
        ]} />

        <Section title="Linki" hint="Wszystkie strony o narzędziu: pola Strona / GitHub / Wikipedia / Cennik oraz dodatkowe linki (np. z notatki w Obsidianie).">
          <ToolLinks links={links} detailed={focusedId !== null} />
          {focusedId !== null && (tool.source_document_id || tool.source_candidate_id) && <div style={{ color: "#64748b", fontSize: ".85rem", marginTop: 6 }}>
            {tool.source_document_id && <span>Dokument źródłowy w Lenie: <Link to={`/read/${tool.source_document_id}`}>#{tool.source_document_id}</Link></span>}
            {tool.source_document_id && tool.source_candidate_id && <span> · </span>}
            {tool.source_candidate_id && <span>Kandydat, z którego powstało: #{tool.source_candidate_id}</span>}
          </div>}
        </Section>

        <Section title="Skąd wiem" hint="Kurs, szkolenie, newsletter, kanał… — skąd o tym narzędziu wiem. Źródła i ich ocenę znajdziesz na stronie Źródła.">
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, fontSize: ".85rem" }}>
            {sources.map(source => <span key={source.id} title={source.context ?? undefined}
              style={{ background: "#ecfeff", color: "#155e75", borderRadius: 4, padding: "2px 7px" }}>
              <Link to="/sources" style={{ color: "inherit" }}>{source.name}</Link>
              {source.context && source.context.startsWith("http") && <> · <a href={source.context} target="_blank" rel="noreferrer" style={{ color: "inherit" }}>link</a></>}
              <button type="button" aria-label={`Usuń źródło ${source.name}`} disabled={savingId === tool.id}
                style={{ border: 0, background: "none", cursor: "pointer", color: "inherit", marginLeft: 4 }}
                onClick={() => void removeSource(tool, source)}>×</button>
            </span>)}
            {!sources.length && sourceToolId !== tool.id && <span style={{ color: "#94a3b8" }}>nie zapisano</span>}
            {sourceToolId === tool.id
              ? <>
                <input list={`known-sources-${tool.id}`} value={sourceDraft} placeholder="nazwa kursu, newslettera…" disabled={savingId === tool.id}
                  onChange={event => setSourceDraft(event.target.value)}
                  onKeyDown={event => { if (event.key === "Enter") void addSource(tool); }} />
                <datalist id={`known-sources-${tool.id}`}>{knownSources.map(source => <option key={source.name} value={source.name} />)}</datalist>
                <button type="button" disabled={savingId === tool.id || !sourceDraft.trim()} onClick={() => void addSource(tool)}>Dodaj</button>
                <button type="button" onClick={() => { setSourceToolId(null); setSourceDraft(""); }}>Anuluj</button>
              </>
              : <button type="button" onClick={() => openSourcePicker(tool)}>+ źródło</button>}
          </div>
        </Section>

        {radar.length > 0 && <Section title="Na radarze" hint="Dlaczego to narzędzie trafiło na Radar narzędzi (dane z wpisu radaru, nie kopia).">
          {radar.map(origin => <div key={origin.id} style={{ color: "#475569", fontSize: ".88rem" }}>
            <Chip tone="info">{radarStatusLabel[origin.status] ?? origin.status}</Chip>
            {origin.source_context && <> {origin.source_context}</>}
            {origin.source_document && <> · <DocumentLink document={origin.source_document} /></>}
            {origin.source_url && origin.source_url.startsWith("http") && <> · <a href={origin.source_url} target="_blank" rel="noreferrer">źródło</a></>}
            {focusedId !== null && origin.evidences.length > 0 && <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
              {origin.evidences.map((evidence, index) => <li key={index}>
                {evidence.relation_type === "listed_in" ? "Na liście" : "Wspomniane w"}{" "}
                {evidence.catalog_url ? <a href={evidence.catalog_url} target="_blank" rel="noreferrer">{evidence.catalog_label ?? evidence.catalog_url}</a> : evidence.catalog_label}
                {evidence.context && <> ({evidence.context})</>}
                {evidence.recommender_document && <> · <DocumentLink document={evidence.recommender_document} /></>}
              </li>)}
              {origin.evidence_count > origin.evidences.length && <li>…i {origin.evidence_count - origin.evidences.length} więcej</li>}
            </ul>}
          </div>)}
        </Section>}

        <Section title="Notatka" hint="Twoja notatka o narzędziu — pisana i edytowana w Lenie.">
          {editingId === tool.id ? <div>
            <MarkdownEditor label={`Notatka o ${tool.name}`} value={draft} onChange={setDraft} toolName={tool.name} disabled={savingId === tool.id} />
            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              <button className="button" type="button" disabled={savingId === tool.id} onClick={() => void saveNote(tool)}>Zapisz notatkę</button>
              <button type="button" disabled={savingId === tool.id} onClick={() => setEditingId(null)}>Anuluj</button>
            </div>
          </div> : <div>
            {tool.personal_notes
              ? <div style={{ margin: "0 0 6px", borderLeft: "3px solid #cbd5e1", paddingLeft: 14 }}><MarkdownView text={tool.personal_notes} /></div>
              : <div style={{ color: "#64748b", fontSize: ".85rem", marginBottom: 6 }}>Brak notatki — napisz, do czego używasz tego narzędzia.</div>}
            <button type="button" onClick={() => { setEditingId(tool.id); setDraft(tool.personal_notes ?? ""); }}>{tool.personal_notes ? "Edytuj notatkę" : "Dodaj notatkę"}</button>
          </div>}
        </Section>

        <ToolRelations relations={tool.relations ?? []} onReview={(id, status) => void reviewRelation(id, status)} />

        {detailsId === tool.id && detailsDraft ? <div style={{ border: "1px dashed #cbd5e1", borderRadius: 8, padding: 12, margin: "14px 0 0" }}>
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
            Dodatkowe linki (jeden w wierszu: adres albo „Etykieta | adres”)
            <textarea rows={3} value={detailsDraft.links} disabled={savingId === tool.id}
              onChange={event => setDetailsDraft({ ...detailsDraft, links: event.target.value })} />
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
        </div> : <div style={{ margin: "14px 0 0" }}>
          <button type="button" onClick={() => { setDetailsId(tool.id); setDetailsDraft(draftFromTool(tool)); }}>Edytuj dane</button>
          {tool.obsidian_note_path && <button type="button" style={{ marginLeft: 8 }} disabled={savingId === tool.id}
            title="Czyta notatkę z vaulta Obsidian (szablon opisu aplikacji) i uzupełnia tylko puste pola: do czego służy, system, licencję, linki, cennik, punkty, polecenia i źródła."
            onClick={() => void importNote(tool)}>Wczytaj z notatki</button>}
          {importMessage?.id === tool.id && <span role="status" style={{ marginLeft: 10, color: "#166534", fontSize: ".85rem" }}>{importMessage.text}</span>}
        </div>}

        <footer style={{ color: "#94a3b8", fontSize: ".8rem", marginTop: 12, display: "flex", flexWrap: "wrap", gap: 14 }}>
          {tool.obsidian_note_path && <span>Notatka w Obsidianie: {tool.obsidian_note_path}</span>}
          {shortDate(tool.created_at) && <span>Dodano: {shortDate(tool.created_at)}</span>}
        </footer>
      </article>;
    })}
  </section>;
}
