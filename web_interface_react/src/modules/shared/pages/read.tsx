import React from "react";
import { useParams, useSearchParams, NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import {
  NotePopover, NoteRow, PendingNote, ReaderIdentityBadge, STANCE_ICON, UserNote,
  normalizeWs, pendingNoteFromSelection, useReaderIdentity, useUserNotes,
} from "../components/ReaderNotes/readerNotes";
import type { CountryTag, PipelineLine, PlaceMarker } from "../components/CountryMap/countryMap";
import { EntityChips, EntityItem } from "../components/EntitiesPanel/entitiesPanel";
import TimelinePanel, { type EventItem } from "../components/TimelinePanel/timelinePanel";
import TimePeriodsPanel from "../components/TimePeriodsPanel/timePeriodsPanel";
import TonePanel from "../components/TonePanel/tonePanel";
import { useIsDesktop } from "../hooks/useIsDesktop";
import styles from "./read.module.css";

// Lazy-loaded: leaflet (~150 kB) should not land in the main bundle for users
// who never open a geopolitical article on desktop (mobile, other pages).
const CountryMap = React.lazy(() => import("../components/CountryMap/countryMap"));

// ── Types ────────────────────────────────────────────────────────────────────

interface Chapter {
  position: number;
  level: number;
  title: string;
  length: number;
  // Present for markdown-header chapters; absent for the TEMAT-chunk fallback
  // used by documents with no H1/H2 structure (YouTube/movie transcripts).
  char_start?: number;
  char_end?: number;
}

// Footnote extracted out of the book text (document_references) — rendered
// as a "Przypisy" section at the end of the chapter, linked from ¹⁸ markers.
interface ChapterReference {
  marker: string;
  text: string;
  url: string | null;
}

interface ChapterContent {
  position: number;
  title: string;
  text: string;
  chapter_total: number;
  references?: ChapterReference[];
  // Synthesis of a run analysed with this chapter as scope (GET /document/:id/chapter/:pos) —
  // takes priority over the whole-document synthesis from GET /document/:id/chapters.
  synthesis_chapter?: string | null;
  prev: number | null;
  next: number | null;
}

// Chapter-scoped sidebar data (GET /document/:id/chapter/:pos/entities) —
// document-level entities/countries filtered down to the chapter being read.
interface ChapterScope {
  persons: EntityItem[];
  placeItems: EntityItem[];
  markers: PlaceMarker[];
  countries: CountryTag[];
}

interface InformationSourceLink {
  id: number;
  source_id: number;
  canonical_name: string;
  domain: string | null;
  role: string;
  source_url: string | null;
  evidence_excerpt: string | null;
}

interface CitedPublicationLink {
  id: number;
  publication_id: number;
  title: string | null;
  pmid: string | null;
  pmcid: string | null;
  doi: string | null;
  canonical_url: string;
  raw_citation: string;
}

interface DocQuality {
  score: number;
  penalties: Record<string, number>;
  llm_rubric?: { zrodla: number; glebia: number; jezyk: number; uzasadnienie?: string } | null;
}

const QUALITY_PENALTY_LABELS: Record<string, string> = {
  photo_captions: "podpisy zdjęć",
  missing_author: "brak autora",
  noise_share: "udział reklam/szumu",
  short_text: "bardzo krótki tekst",
  clickbait_title: "clickbaitowy tytuł",
  llm_rubric: "rubryka LLM (źródła/głębia/język)",
};

function qualityTooltip(q: DocQuality): string {
  const lines = Object.entries(q.penalties ?? {}).map(
    ([key, pts]) => `−${pts}: ${QUALITY_PENALTY_LABELS[key] ?? key}`,
  );
  if (lines.length === 0) lines.push("bez zastrzeżeń");
  if (q.llm_rubric) {
    lines.push(`LLM — źródła: ${q.llm_rubric.zrodla}/5, głębia: ${q.llm_rubric.glebia}/5, język: ${q.llm_rubric.jezyk}/5`);
    if (q.llm_rubric.uzasadnienie) lines.push(q.llm_rubric.uzasadnienie);
  }
  return lines.join("\n");
}

function qualityColors(score: number): React.CSSProperties {
  if (score >= 75) return { background: "#dcfce7", color: "#15803d" };
  if (score >= 50) return { background: "#fef3c7", color: "#b45309" };
  return { background: "#fee2e2", color: "#b91c1c" };
}

const SOURCE_ROLE_LABELS: Record<string, string> = {
  publisher: "Publikacja",
  original_reporting: "Źródło ustaleń",
  republication: "Przedruk / opracowanie",
  cited: "Cytowane źródło",
  data_source: "Źródło danych",
};

// ── Minimal markdown rendering (headings, paragraphs, hr; images skipped) ────

const IMAGE_LINE = /^!\[[^\]]*\]\([^)]*\)$/;

/** Footnote text with its URL fragment rendered as a link. The backend stores
 *  the first URL it found in the footnote (normalized to https://), so the
 *  matching fragment in the visible text becomes clickable; when the fragment
 *  can't be located (edge cases), a trailing 🔗 keeps the link reachable. */
function renderRefText(r: ChapterReference): React.ReactNode {
  if (!r.url) return r.text;
  const bare = r.url.replace(/^https?:\/\//, "");
  const full = r.text.indexOf(r.url);
  const idx = full >= 0 ? full : r.text.indexOf(bare);
  const frag = full >= 0 ? r.url : bare;
  if (idx < 0) {
    return <>{r.text}{" "}<a href={r.url} target="_blank" rel="noreferrer" title={r.url}>🔗</a></>;
  }
  return (
    <>
      {r.text.slice(0, idx)}
      <a href={r.url} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all", color: "#0369a1" }}>
        {frag}
      </a>
      {r.text.slice(idx + frag.length)}
    </>
  );
}

const SUP_TO_DIGIT: Record<string, string> = {
  "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
};
const supToNumber = (sup: string) => sup.split("").map(c => SUP_TO_DIGIT[c] ?? "").join("");

function renderInline(text: string, refs?: Map<string, ChapterReference>): React.ReactNode[] {
  // **bold**, *italic* and ¹⁸ footnote markers — enough for OCR-ed book prose
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|[¹²³⁴⁵⁶⁷⁸⁹⁰]+)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
    if (/^[¹²³⁴⁵⁶⁷⁸⁹⁰]+$/.test(part)) {
      const ref = refs?.get(supToNumber(part));
      if (ref) {
        return (
          <sup key={i}>
            <a href={`#fn-${ref.marker}`} title={ref.text} style={{ textDecoration: "none", color: "#0369a1" }}>
              {part}
            </a>
          </sup>
        );
      }
      return part;
    }
    return part;
  });
}

// All complete-token occurrences of the given terms. Terms are matched
// case-insensitively at Unicode-aware boundaries, except that a capitalized
// term only matches a capitalized surface form. Longer overlapping terms win.
function findEntityMatches(text: string, terms: string[]): { idx: number; len: number }[] {
  const uniqueTerms = new Map<string, string>();
  terms.forEach(rawTerm => {
    const term = rawTerm.trim();
    const key = term.toLowerCase();
    if (term.length >= 2 && !uniqueTerms.has(key)) uniqueTerms.set(key, term);
  });
  const sortedTerms = [...uniqueTerms.values()].sort((a, b) => b.length - a.length);
  if (!sortedTerms.length) return [];

  const escaped = sortedTerms.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(
    `(?<![\\p{L}\\p{N}_])(?:${escaped.join("|")})(?![\\p{L}\\p{N}_])`,
    "giu",
  );
  return [...text.matchAll(pattern)]
    .filter(match => {
      const matchedText = match[0];
      const term = uniqueTerms.get(matchedText.toLowerCase());
      return term && (!isUppercaseLetter(term[0]) || isUppercaseLetter(matchedText[0]));
    })
    .map(match => ({ idx: match.index!, len: match[0].length }));
}

function isUppercaseLetter(char: string): boolean {
  return char === char.toUpperCase() && char !== char.toLowerCase();
}

function entityHighlightTerms(item: EntityItem): string[] {
  if (item.chapter_variants?.length) return item.chapter_variants;
  if (item.variants?.length) return item.variants;
  return [item.text];
}

function normalizeAnchorText(value: string): string {
  return normalizeWs(value)
    .replace(/[‐‑‒–—−]/g, "-")
    .replace(/[“”„‟«»]/g, '"')
    .replace(/[‘’‚‛]/g, "'");
}

/** Render anchored note/timeline quotes and entity terms. Exact anchor match
 *  becomes an inline highlight; whitespace/typography-normalized anchor match
 *  tints the whole paragraph (quote spans line breaks or renderer differences). */
function renderParagraphWithNotes(
  text: string,
  notes: UserNote[],
  refs?: Map<string, ChapterReference>,
  highlightTerms?: string[],
  timelineAnchor?: string | null,
): { nodes: React.ReactNode[]; paragraphTint: UserNote | null; timelineTint: boolean; timelineFound: boolean } {
  type Match = { idx: number; len: number; kind: "note" | "entity" | "timeline"; note?: UserNote };
  const noteMatches: Match[] = notes
    .map(n => ({ note: n, idx: text.indexOf(n.anchor_quote), len: n.anchor_quote.length, kind: "note" as const }))
    .filter(m => m.idx >= 0);
  const entityMatches: Match[] = findEntityMatches(text, highlightTerms ?? [])
    .map(m => ({ ...m, kind: "entity" as const }));
  const timelineIndex = timelineAnchor ? text.indexOf(timelineAnchor) : -1;
  const timelineMatches: Match[] = timelineAnchor && timelineIndex >= 0
    ? [{ idx: timelineIndex, len: timelineAnchor.length, kind: "timeline" }]
    : [];
  const matches = [...timelineMatches, ...noteMatches, ...entityMatches].sort((a, b) => a.idx - b.idx);
  const paragraphTint = notes.find(n =>
    text.indexOf(n.anchor_quote) < 0
    && normalizeAnchorText(text).includes(normalizeAnchorText(n.anchor_quote))) ?? null;
  const timelineTint = Boolean(
    timelineAnchor && timelineIndex < 0
    && normalizeAnchorText(text).includes(normalizeAnchorText(timelineAnchor)),
  );
  const timelineFound = timelineIndex >= 0 || timelineTint;

  if (matches.length === 0) {
    return { nodes: renderInline(text, refs), paragraphTint, timelineTint, timelineFound };
  }

  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  matches.forEach((m, i) => {
    if (m.idx < cursor) return; // overlapping match — skip
    if (m.idx > cursor) nodes.push(...renderInline(text.slice(cursor, m.idx), refs));
    const quoted = text.slice(m.idx, m.idx + m.len);
    if (m.kind === "note" && m.note) {
      nodes.push(
        <mark
          key={`note-${m.note.id}-${i}`}
          title={`${STANCE_ICON[m.note.stance ?? ""] ?? "📝"} ${m.note.note_text}`}
          style={{ background: "#fef08a", padding: "0 1px", cursor: "help" }}
        >
          {renderInline(quoted, refs)}
        </mark>
      );
    } else if (m.kind === "timeline") {
      nodes.push(
        <mark
          key={`timeline-${i}`}
          className="timeline-highlight"
          style={{ background: "#fed7aa", padding: "0 1px" }}
        >
          {renderInline(quoted, refs)}
        </mark>
      );
    } else {
      nodes.push(
        <mark
          key={`ent-${i}`}
          className="entity-highlight"
          style={{ background: "#bfdbfe", padding: "0 1px" }}
        >
          {renderInline(quoted, refs)}
        </mark>
      );
    }
    cursor = m.idx + m.len;
  });
  if (cursor < text.length) nodes.push(...renderInline(text.slice(cursor), refs));
  return { nodes, paragraphTint, timelineTint, timelineFound };
}

function renderMarkdown(
  text: string,
  notes: UserNote[],
  refs?: Map<string, ChapterReference>,
  highlightTerms?: string[],
  timelineAnchor?: string | null,
): React.ReactNode[] {
  const blocks = text.split(/\n\s*\n/);
  const out: React.ReactNode[] = [];
  blocks.forEach((block, i) => {
    const trimmed = block.trim();
    if (!trimmed || IMAGE_LINE.test(trimmed)) return;
    const heading = trimmed.match(/^(#{1,6})\s+(.*)$/s);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 6);
      const Tag = `h${level}` as keyof JSX.IntrinsicElements;
      // headings can carry note anchors too (e.g. a quote of the chapter title)
      const { nodes, timelineTint, timelineFound } = renderParagraphWithNotes(
        heading[2].replace(/\n/g, " "), notes, undefined, highlightTerms, timelineAnchor,
      );
      out.push(
        <Tag
          key={i}
          className={timelineFound ? "timeline-anchor-paragraph" : undefined}
          style={{ marginTop: level === 2 ? 0 : 28, ...(timelineTint ? { background: "#fff7ed" } : {}) }}
        >
          {nodes}
        </Tag>,
      );
      return;
    }
    if (trimmed === "---") {
      out.push(<hr key={i} style={{ margin: "20px 0", border: "none", borderTop: "1px solid #e2e8f0" }} />);
      return;
    }
    // footnote / caption lines (superscript digits or "Wykres N.") — smaller font
    const isNote = /^([¹²³⁴⁵⁶⁷⁸⁹⁰]+|\d{1,3} )\S*\s*(http|www|[A-ZŻŹĆĄŚĘŁÓŃ])/.test(trimmed) && trimmed.length < 400;
    const paraText = trimmed.replace(/\n/g, " ");
    const { nodes, paragraphTint, timelineTint, timelineFound } = renderParagraphWithNotes(
      paraText, notes, refs, highlightTerms, timelineAnchor,
    );
    out.push(
      <p key={i} className={timelineFound ? "timeline-anchor-paragraph" : undefined} style={isNote
        ? { fontSize: "0.8em", color: "#64748b", margin: "6px 0" }
        : {
            lineHeight: 1.65, margin: "14px 0", textAlign: "justify",
            ...(paragraphTint ? { background: "#fefce8", borderLeft: "3px solid #eab308", paddingLeft: 8 } : {}),
            ...(timelineTint ? { background: "#fff7ed", borderLeft: "3px solid #f59e0b", paddingLeft: 8 } : {}),
          }}
        title={paragraphTint ? `📝 ${paragraphTint.note_text}` : undefined}>
        {nodes}
      </p>
    );
  });
  return out;
}

// Document types that have an editor page at /{type}/:id
const EDITOR_TYPES = new Set(["webpage", "link", "youtube", "movie", "email"]);

// Tag counts above this render the sidebar "Tagi" section collapsed by default.
const TAGS_OPEN_THRESHOLD = 20;

// ── Page ─────────────────────────────────────────────────────────────────────

const Read: React.FC = () => {
  const { id } = useParams();
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();

  const [chapters, setChapters] = React.useState<Chapter[]>([]);
  const [readerCompact, setReaderCompact] = React.useState(false);
  const [documentType, setDocumentType] = React.useState<string | null>(null);
  const [countries, setCountries] = React.useState<CountryTag[]>([]);
  const [places, setPlaces] = React.useState<PlaceMarker[]>([]);
  const [personItems, setPersonItems] = React.useState<EntityItem[]>([]);
  const [placeItems, setPlaceItems] = React.useState<EntityItem[]>([]);
  // Set when the last NER refresh found ner_service unreachable (backend:
  // web_documents.ner_unavailable_at) — distinguishes "service was down" from
  // "genuinely no persons/places in this document" so the reader can warn
  // instead of just staying silently empty.
  const [nerUnavailableAt, setNerUnavailableAt] = React.useState<string | null>(null);
  const [thematicTags, setThematicTags] = React.useState<string[]>([]);
  const [synthesis, setSynthesis] = React.useState<string | null>(null);
  const [informationSources, setInformationSources] = React.useState<InformationSourceLink[]>([]);
  const [citedPublications, setCitedPublications] = React.useState<CitedPublicationLink[]>([]);
  const [docQuality, setDocQuality] = React.useState<DocQuality | null>(null);
  const [docUrl, setDocUrl] = React.useState<string | null>(null);
  const [docPublishedOn, setDocPublishedOn] = React.useState<string | null>(null);
  const [docCreatedAt, setDocCreatedAt] = React.useState<string | null>(null);
  const [content, setContent] = React.useState<ChapterContent | null>(null);
  // sidebar scope: current chapter (default) vs whole document
  const [scopeChapter, setScopeChapter] = React.useState(true);
  const [chapterScope, setChapterScope] = React.useState<ChapterScope | null>(null);
  const [chapterScopeLoading, setChapterScopeLoading] = React.useState(false);
  const chapterScopeRequestId = React.useRef(0);
  const contentRequestId = React.useRef(0);
  // sidebar chip click mode: highlight the entity in the chapter text (default)
  // vs the previous behaviour of navigating to /persons/:id or a search
  const [highlightMode, setHighlightMode] = React.useState(true);
  // terms to <mark> in the chapter text — seeded from ?highlight= (set by the
  // persons page's document links, using the document's raw_mention) or a
  // sidebar chip click (which supplies the entity's known surface variants)
  const [highlightTerms, setHighlightTerms] = React.useState<string[]>(() => {
    const h = searchParams.get("highlight");
    return h ? [h] : [];
  });
  const [timelineHighlight, setTimelineHighlight] = React.useState<{
    quote: string;
    dateText: string;
    chapterPosition: number | null;
  } | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [tocOpen, setTocOpen] = React.useState(false);
  const contentRef = React.useRef<HTMLDivElement>(null);
  const isDesktop = useIsDesktop();

  // ── Reading progress ──
  const [readChapters, setReadChapters] = React.useState<number[]>([]);
  const [progressLoaded, setProgressLoaded] = React.useState(false);
  const initialRedirectDone = React.useRef(false);

  // ── User identity + notes (shared with /chunks) ──
  const identity = useReaderIdentity(apiUrl, apiKey, () => {
    setProgressLoaded(false);
    initialRedirectDone.current = false;
  });
  const { userId, headers, jsonHeaders } = identity;
  const { notes, createNote, saveNoteText, deleteNote } = useUserNotes(apiUrl, id, identity);
  const [pendingNote, setPendingNote] = React.useState<PendingNote | null>(null);
  const [tagQuery, setTagQuery] = React.useState("");
  const [tagResults, setTagResults] = React.useState<UserNote[]>([]);

  const requestedPosition = Number(searchParams.get("chapter") ?? 1);
  const position = readerCompact ? 1 : requestedPosition;

  // ── Data loading ──

  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/chapters?reader=1`, { headers });
        const data = await r.json();
        if (data.status !== "success") throw new Error(data.message ?? "Błąd pobierania rozdziałów");
        setChapters(data.chapters ?? []);
        setReaderCompact(data.reader_compact === true);
        setScopeChapter(data.reader_compact !== true);
        if (data.reader_compact === true && requestedPosition !== 1) {
          const next = new URLSearchParams(searchParams);
          next.set("chapter", "1");
          setSearchParams(next, { replace: true });
        }
        setDocumentType(data.document_type ?? null);
        setCountries(data.countries ?? []);
        setThematicTags(data.thematic_tags ?? []);
        setSynthesis(data.synthesis ?? null);
        setDocQuality(data.quality ?? null);
        setDocUrl(data.url ?? null);
        setDocPublishedOn(data.published_on ?? null);
        setDocCreatedAt(data.created_at ?? null);
      } catch (e) {
        setError(String(e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, apiKey]);

  React.useEffect(() => {
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/document/${id}/information_sources`, { headers });
        const data = await response.json();
        if (data.status === "success") setInformationSources(data.entries ?? []);
      } catch {
        // Provenance enriches the reader but must not block document reading.
      }
    })();
  }, [apiUrl, id, apiKey]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/document/${id}/cited_publications`, { headers });
        const data = await response.json();
        if (data.status === "success") setCitedPublications(data.entries ?? []);
      } catch { /* Citations are optional reader enrichment. */ }
    })();
  }, [apiUrl, id, apiKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // verified NER places (stage 3) → point markers on the country map
  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/website_entities?id=${id}`, { headers });
        const data = await r.json();
        if (data.status !== "success") return;
        const items = [...(data.entities?.geogName ?? []), ...(data.entities?.placeName ?? [])];
        setPersonItems(data.entities?.persName ?? []);
        setPlaceItems(items);
        setNerUnavailableAt(data.ner_unavailable_at ?? null);
        setPlaces(
          items
            .filter((it: any) => it.verified === true && it.lat != null && it.lon != null)
            .map((it: any) => ({ name: it.text, lat: it.lat, lon: it.lon })),
        );
      } catch {
        // encje są ozdobnikiem widoku — brak nie blokuje czytnika
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, apiKey]);

  // chapter-scoped sidebar data — refetched when the reader moves to another
  // chapter; a failure falls back to the document-level entities (scope null)
  React.useEffect(() => {
    if (!scopeChapter || !progressLoaded) {
      chapterScopeRequestId.current += 1;
      setChapterScopeLoading(false);
      return;
    }
    const requestId = ++chapterScopeRequestId.current;
    setChapterScope(null);
    setChapterScopeLoading(true);
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/chapter/${position}/entities?reader=1`, { headers });
        const data = await r.json();
        if (requestId !== chapterScopeRequestId.current) return;
        if (data.status !== "success") { setChapterScope(null); return; }
        const items = [...(data.entities?.geogName ?? []), ...(data.entities?.placeName ?? [])];
        setChapterScope({
          persons: data.entities?.persName ?? [],
          placeItems: items,
          markers: items
            .filter((it: any) => it.verified === true && it.lat != null && it.lon != null)
            .map((it: any) => ({ name: it.text, lat: it.lat, lon: it.lon })),
          countries: data.countries ?? [],
        });
      } catch {
        if (requestId === chapterScopeRequestId.current) setChapterScope(null);
      } finally {
        if (requestId === chapterScopeRequestId.current) setChapterScopeLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, position, scopeChapter, progressLoaded, apiKey]);

  // Resolve a raw ?highlight= mention to the variants that actually occur in
  // the loaded chapter. This keeps arrivals from the persons page aligned with
  // the same exact-token matching used by chapter-scoped sidebar clicks.
  React.useEffect(() => {
    const requested = searchParams.get("highlight")?.trim().toLowerCase();
    if (!requested || !chapterScope) return;
    const items = [...chapterScope.persons, ...chapterScope.placeItems];
    const item = items.find(candidate =>
      [candidate.text, ...(candidate.variants ?? [])].some(value => value.trim().toLowerCase() === requested));
    if (item) setHighlightTerms(entityHighlightTerms(item));
  }, [chapterScope, searchParams]);

  // progress: fetch once per (user, doc); redirect to last position when URL has no ?chapter
  React.useEffect(() => {
    if (!userId) { setProgressLoaded(true); setReadChapters([]); return; }
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/reading_progress`, { headers });
        const data = await r.json();
        if (data.status === "success") {
          setReadChapters(data.read_chapters ?? []);
          if (!initialRedirectDone.current && !searchParams.get("chapter") && data.current_chapter) {
            // preserve other params (e.g. ?highlight= from the persons page)
            setSearchParams((prev) => {
              const next = new URLSearchParams(prev);
              next.set("chapter", String(data.current_chapter));
              return next;
            }, { replace: true });
          }
        }
      } catch { /* progress is best-effort */ }
      initialRedirectDone.current = true;
      setProgressLoaded(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, userId]);

  // chapter content — waits for the progress redirect so we don't flash chapter 1
  React.useEffect(() => {
    if (!progressLoaded) return;
    const requestId = ++contentRequestId.current;
    (async () => {
      setLoading(true);
      setError(null);
      setPendingNote(null);
      try {
        const r = await fetch(`${apiUrl}/document/${id}/chapter/${position}?reader=1`, { headers });
        const data = await r.json();
        if (requestId !== contentRequestId.current) return;
        if (data.status !== "success") throw new Error(data.message ?? "Błąd pobierania rozdziału");
        setContent(data);
        contentRef.current?.scrollTo({ top: 0 });
        window.scrollTo({ top: 0 });
      } catch (e) {
        if (requestId === contentRequestId.current) setError(String(e));
      } finally {
        if (requestId === contentRequestId.current) setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, position, progressLoaded, apiKey]);

  // persist current chapter as reading position
  React.useEffect(() => {
    if (!userId || !content || !progressLoaded) return;
    fetch(`${apiUrl}/document/${id}/reading_progress`, {
      method: "PUT", headers: jsonHeaders,
      body: JSON.stringify({ current_chapter: content.position, current_chapter_title: content.title }),
    }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content?.position, userId]);

  // scroll the first highlighted entity match into view — covers both a
  // fresh arrival from the persons page (?highlight=) and a sidebar chip click.
  // Delayed a tick: the chapter-load path scrolls to top right after setContent
  // and the lazy map shifts layout, either of which cancels an immediate scroll.
  React.useEffect(() => {
    if (!highlightTerms.length || !content) return;
    const t = window.setTimeout(() => {
      const el = contentRef.current?.querySelector<HTMLElement>(".entity-highlight");
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 300);
    return () => window.clearTimeout(t);
  }, [content, highlightTerms]);

  // Timeline anchors deliberately use the note-anchor rendering path, not
  // token-based entity matching. Exact quotes get an inline mark; normalized
  // whitespace/typography matches tint the containing paragraph.
  React.useEffect(() => {
    if (!timelineHighlight || !content) return;
    if (timelineHighlight.chapterPosition != null && content.position !== timelineHighlight.chapterPosition) return;
    const t = window.setTimeout(() => {
      const el = contentRef.current?.querySelector<HTMLElement>(
        ".timeline-highlight, .timeline-anchor-paragraph",
      );
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 300);
    return () => window.clearTimeout(t);
  }, [content, timelineHighlight]);

  // ── Actions ──

  const goTo = (pos: number | null) => {
    if (pos) {
      // a new chapter is a new context — drop the entity highlight
      setHighlightTerms([]);
      setTimelineHighlight(null);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("chapter", String(pos));
        next.delete("highlight");
        return next;
      });
    }
    setTocOpen(false);
  };

  const clearHighlight = () => {
    setHighlightTerms([]);
    const next = new URLSearchParams(searchParams);
    next.delete("highlight");
    setSearchParams(next, { replace: true });
  };

  // sidebar chip click in highlight mode — mark the entity's known surface
  // variants (chapter-scoped chips carry them) or fall back to its label
  const handleEntityHighlight = (item: EntityItem) => {
    setTimelineHighlight(null);
    setHighlightTerms(entityHighlightTerms(item));
    const next = new URLSearchParams(searchParams);
    next.set("highlight", item.text);
    setSearchParams(next, { replace: true });
  };

  const handleTimelineEventClick = (event: EventItem) => {
    setHighlightTerms([]);
    const quote = event.anchor_quote?.trim();
    setTimelineHighlight(quote ? {
      quote,
      dateText: event.date_text,
      chapterPosition: event.chapter_position,
    } : null);
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (event.chapter_position != null) next.set("chapter", String(event.chapter_position));
      next.delete("highlight");
      return next;
    });
    setTocOpen(false);
  };

  const toggleRead = (pos: number, read: boolean) => {
    if (!userId) return;
    setReadChapters(prev => read ? [...prev, pos].sort((a, b) => a - b) : prev.filter(p => p !== pos));
    fetch(`${apiUrl}/document/${id}/reading_progress`, {
      method: "PUT", headers: jsonHeaders,
      body: JSON.stringify({
        current_chapter: position,
        [read ? "mark_read" : "unmark_read"]: [pos],
      }),
    }).catch(() => undefined);
  };

  const goNext = () => {
    if (!content?.next) return;
    if (userId && !readChapters.includes(content.position)) toggleRead(content.position, true);
    goTo(content.next);
  };

  const onTextContextMenu = (event: React.MouseEvent<HTMLElement>) => {
    if (!userId) return;
    const pending = pendingNoteFromSelection("p");
    if (pending) {
      event.preventDefault();
      setPendingNote({ ...pending, x: event.pageX, y: event.pageY });
    }
  };

  const saveNote = async (noteText: string, stance: string | null, tags: string[]) => {
    if (!pendingNote || (!noteText && tags.length === 0)) return;
    const ok = await createNote({
      anchor_quote: pendingNote.quote,
      anchor_prefix: pendingNote.prefix,
      anchor_suffix: pendingNote.suffix,
      chapter_position: position,
      note_text: noteText,
      tags,
      stance,
    });
    if (ok) setPendingNote(null);
  };

  const searchSelectedQuote = (quote: string) => {
    window.open(`/search?q=${encodeURIComponent(quote)}`, "_blank", "noopener,noreferrer");
    setPendingNote(null);
  };

  const searchByTag = async (tag: string) => {
    const normalized = tag.trim().toLowerCase().replace(/^#/, "");
    if (!normalized) { setTagResults([]); return; }
    const r = await fetch(`${apiUrl}/notes?tag=${encodeURIComponent(normalized)}`, { headers });
    const data = await r.json();
    setTagResults(data.status === "success" ? (data.notes ?? []) : []);
  };

  // ── Derived ──

  const chapterNotes = React.useMemo(
    () => content?.chapter_total === 1
      ? notes
      : notes.filter(n => n.chapter_position === position),
    [notes, position, content?.chapter_total]);

  // footnotes by marker — for ¹⁸ tooltips/anchors in the text
  const referencesByMarker = React.useMemo(
    () => new Map((content?.references ?? []).map(r => [r.marker, r])),
    [content?.references]);

  const anchoredNoteIds = React.useMemo(() => {
    if (!content) return new Set<number>();
    const normText = normalizeWs(content.text);
    return new Set(
      chapterNotes.filter(n => normText.includes(normalizeWs(n.anchor_quote))).map(n => n.id));
  }, [content, chapterNotes]);

  // sidebar data in the selected scope — chapter scope falls back to
  // document-level values until the chapter fetch lands (or when it fails)
  const scoped = scopeChapter ? chapterScope : null;
  const shownPersons = scoped ? scoped.persons : personItems;
  const shownPlaceItems = scoped ? scoped.placeItems : placeItems;
  const shownMarkers = scoped ? scoped.markers : places;
  const shownCountries = scoped ? scoped.countries : countries;
  // pipeline routes (Overpass/OSM) among the in-scope place entities
  const shownPipelines: PipelineLine[] = shownPlaceItems
    .filter(it => it.pipeline?.geojson?.coordinates?.length)
    .map(it => ({
      name: it.pipeline!.name ?? it.text,
      substance: it.pipeline!.substance,
      coordinates: it.pipeline!.geojson!.coordinates,
    }));
  const rightPanelLoading = loading || (scopeChapter && chapterScopeLoading);

  // ── Render ──

  const navButtons = content && content.chapter_total > 1 && (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, margin: "18px 0" }}>
      <button onClick={() => goTo(content.prev)} disabled={!content.prev}
        style={{ padding: "6px 14px", cursor: content.prev ? "pointer" : "default" }}>
        ← Poprzedni
      </button>
      <span style={{ fontSize: "0.85em", color: "#64748b", alignSelf: "center" }}>
        {content.position} / {content.chapter_total}
      </span>
      <button onClick={goNext} disabled={!content.next}
        style={{ padding: "6px 14px", cursor: content.next ? "pointer" : "default" }}>
        Następny →
      </button>
    </div>
  );

  const renderNoteRow = (n: UserNote) => (
    <NoteRow
      key={n.id}
      note={n}
      header={<>
        {STANCE_ICON[n.stance ?? ""] ?? "📝"} rozdz. {n.chapter_position ?? "?"}
        {n.chapter_position === position && !anchoredNoteIds.has(n.id) &&
          <span style={{ color: "#b45309" }}> ⚠ nie odnaleziono w tekście</span>}
      </>}
      onHeaderClick={n.chapter_position ? () => goTo(readerCompact ? 1 : n.chapter_position) : undefined}
      onSaveText={saveNoteText}
      onDelete={deleteNote}
    />
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Czytelnik — dokument #{id}</h2>
        {docQuality && (
          <span
            title={qualityTooltip(docQuality)}
            style={{
              fontSize: "0.8em", fontWeight: 700, padding: "2px 9px", borderRadius: 10,
              cursor: "help", ...qualityColors(docQuality.score),
            }}
          >
            ⚖ Staranność: {docQuality.score}/100
          </span>
        )}
        {chapters.length > 1 && (
          <button className={styles.tocToggleButton} onClick={() => setTocOpen(o => !o)}>
            📑 Spis treści ({chapters.length})
          </button>
        )}
        {documentType && EDITOR_TYPES.has(documentType) && (
          <NavLink to={`/${documentType}/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>✏️ Edytuj</NavLink>
        )}
        <NavLink to={`/chunks/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>Przegląd chunków</NavLink>
        <NavLink to="/list" style={{ fontSize: "0.85em", color: "#0369a1" }}>← Lista dokumentów</NavLink>
        <div style={{ marginLeft: "auto" }}><ReaderIdentityBadge identity={identity} /></div>
      </div>

      {(docPublishedOn || docCreatedAt || docUrl) && (
        <div style={{ fontSize: "0.82em", color: "#64748b", marginBottom: 10, display: "flex", gap: 14, flexWrap: "wrap" }}>
          {docPublishedOn && <span>📅 Opublikowano: {new Date(docPublishedOn).toLocaleDateString("pl-PL")}</span>}
          {docCreatedAt && <span>Dodano do Lenie: {new Date(docCreatedAt).toLocaleDateString("pl-PL")}</span>}
          {docUrl && (
            <a href={docUrl} target="_blank" rel="noreferrer" style={{ color: "#0369a1", wordBreak: "break-all" }}>
              🔗 Oryginał ↗
            </a>
          )}
        </div>
      )}

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <div
        className={`${styles.scrim} ${tocOpen ? styles.scrimOpen : ""}`}
        onClick={() => setTocOpen(false)}
      />

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        {/* TOC sidebar + notes */}
        <div className={`${styles.tocPanel} ${tocOpen ? styles.tocPanelOpen : ""}`}>
          {chapters.length > 1 && <nav style={{
            background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 0",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 14px" }}>
              <strong style={{ fontSize: "0.85em" }}>Spis treści ({chapters.length})</strong>
              <button className={styles.tocClose} onClick={() => setTocOpen(false)} aria-label="Zamknij spis treści">✕</button>
            </div>
            {chapters.map(ch => {
              const isRead = readChapters.includes(ch.position);
              return (
                <div key={ch.position}
                  style={{
                    display: "flex", alignItems: "baseline", gap: 6,
                    padding: "5px 8px 5px 14px", fontSize: "0.83em", lineHeight: 1.3,
                    background: ch.position === position ? "#e0f2fe" : undefined,
                    fontWeight: ch.position === position ? 600 : undefined,
                  }}>
                  <span onClick={() => goTo(ch.position)}
                    style={{ cursor: "pointer", flex: 1, color: isRead ? "#94a3b8" : undefined }}>
                    {ch.position === position ? "▶ " : ""}{ch.position}. {ch.title}
                  </span>
                  {userId && (
                    <span
                      title={isRead ? "Oznacz jako nieprzeczytany" : "Oznacz jako przeczytany"}
                      onClick={() => toggleRead(ch.position, !isRead)}
                      style={{ cursor: "pointer", color: isRead ? "#16a34a" : "#cbd5e1" }}>
                      ✓
                    </span>
                  )}
                </div>
              );
            })}
          </nav>}

          {userId && notes.length > 0 && (
            <div style={{
              background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
              marginTop: 12, padding: "10px 0",
            }}>
              <strong style={{ fontSize: "0.85em", padding: "0 14px" }}>📝 Moje notatki ({notes.length})</strong>
              {notes.map(renderNoteRow)}
            </div>
          )}

          {userId && (
            <div style={{
              background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
              marginTop: 12, padding: 10,
            }}>
              <strong style={{ fontSize: "0.85em" }}>🏷️ Szukaj po tagu</strong>
              <form onSubmit={e => { e.preventDefault(); void searchByTag(tagQuery); }}
                style={{ display: "flex", gap: 4, marginTop: 7 }}>
                <input value={tagQuery} onChange={e => setTagQuery(e.target.value)}
                  placeholder="np. ESSI" style={{ minWidth: 0, flex: 1 }} />
                <button type="submit">Szukaj</button>
              </form>
              {tagResults.map(n => (
                <NavLink key={n.id}
                  to={`/read/${n.document_id}?chapter=${n.chapter_position ?? 1}&highlight=${encodeURIComponent(n.anchor_quote)}`}
                  style={{ display: "block", fontSize: "0.78em", marginTop: 7, color: "#0369a1" }}>
                  dokument #{n.document_id}, rozdz. {n.chapter_position ?? "?"}: {n.anchor_quote.slice(0, 70)}
                </NavLink>
              ))}
              {tagQuery && tagResults.length === 0 && (
                <div style={{ color: "#94a3b8", fontSize: "0.75em", marginTop: 6 }}>
                  Wpisz tag i wybierz „Szukaj”.
                </div>
              )}
            </div>
          )}
        </div>

        {/* Chapter content — fixed reading width, does not grow to soak up wide-screen space.
            minWidth: 0 overrides the flex item default (min-width: auto), which would
            otherwise refuse to shrink below the article's content min-content width and
            starve the right column of the space it's supposed to grow into. */}
        <div ref={contentRef} style={{ flex: "0 1 760px", minWidth: 0 }}>
          {navButtons}
          {highlightTerms.length > 0 && (
            <div style={{
              display: "flex", alignItems: "center", gap: 8, margin: "0 0 12px", fontSize: "0.85em",
              color: "#334155",
            }}>
              🔎 Podświetlono: <strong>{highlightTerms[0]}</strong>
              <button type="button" onClick={clearHighlight}
                style={{ border: "none", background: "none", cursor: "pointer", color: "#0369a1", padding: 0 }}>
                ✕ wyczyść
              </button>
            </div>
          )}
          {timelineHighlight && (
            <div style={{
              display: "flex", alignItems: "center", gap: 8, margin: "0 0 12px", fontSize: "0.85em",
              color: "#334155",
            }}>
              🕰️ Wydarzenie: <strong>{timelineHighlight.dateText}</strong>
              <button type="button" onClick={() => setTimelineHighlight(null)}
                style={{ border: "none", background: "none", cursor: "pointer", color: "#0369a1", padding: 0 }}>
                ✕ wyczyść
              </button>
            </div>
          )}
          {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
          {!loading && content && (
            <article style={{ fontSize: "1.02em" }} onContextMenu={onTextContextMenu}>
              {renderMarkdown(
                content.text, chapterNotes, referencesByMarker, highlightTerms, timelineHighlight?.quote,
              )}
            </article>
          )}
          {!loading && content && (content.references?.length ?? 0) > 0 && (
            <details open style={{
              marginTop: 24, padding: "10px 14px", background: "#f8fafc",
              border: "1px solid #e2e8f0", borderRadius: 8,
            }}>
              <summary style={{ cursor: "pointer", fontSize: "0.9em", fontWeight: 600 }}>
                📚 Przypisy ({content.references!.length})
              </summary>
              <ol style={{ fontSize: "0.82em", color: "#475569", lineHeight: 1.5, margin: "8px 0 0", paddingLeft: 28 }}>
                {content.references!.map((r, i) => (
                  <li key={i} id={`fn-${r.marker}`} value={Number(r.marker) || undefined} style={{ margin: "4px 0" }}>
                    {renderRefText(r)}
                  </li>
                ))}
              </ol>
            </details>
          )}
          {navButtons}
        </div>

        {/* Map + entities + tags + synthesis — desktop only */}
        {isDesktop && (
          <div className={styles.rightPanel}>
            {!readerCompact && <div style={{ fontSize: "0.78em", color: "#64748b", display: "flex", gap: 8, alignItems: "center" }}>
              Zakres:
              {([["rozdział", true], ["cały dokument", false]] as const).map(([label, value]) => (
                <button
                  key={label}
                  onClick={() => setScopeChapter(value)}
                  style={{
                    border: "none", background: "none", cursor: "pointer", padding: 0,
                    fontSize: "1em",
                    color: scopeChapter === value ? "#0369a1" : "#94a3b8",
                    fontWeight: scopeChapter === value ? 600 : undefined,
                    textDecoration: scopeChapter === value ? undefined : "underline",
                  }}>
                  {label}
                </button>
              ))}
            </div>}
            <div style={{
              fontSize: "0.78em", color: "#64748b", display: "flex", gap: 8, alignItems: "center", marginTop: 4,
            }}>
              Tryb kliknięcia:
              {([["podświetl w tekście", true], ["szukaj w bazie", false]] as const).map(([label, value]) => (
                <button
                  key={label}
                  onClick={() => setHighlightMode(value)}
                  title={value ? "Kliknięcie chipa podświetla wystąpienia w tekście rozdziału"
                    : "Kliknięcie chipa przechodzi do strony osoby lub wyszukiwania"}
                  style={{
                    border: "none", background: "none", cursor: "pointer", padding: 0,
                    fontSize: "1em",
                    color: highlightMode === value ? "#0369a1" : "#94a3b8",
                    fontWeight: highlightMode === value ? 600 : undefined,
                    textDecoration: highlightMode === value ? undefined : "underline",
                  }}>
                  {label}
                </button>
              ))}
            </div>
            {rightPanelLoading ? (
              <div role="status" aria-live="polite" style={{
                minHeight: 160, display: "flex", alignItems: "center",
                justifyContent: "center", gap: 8, color: "#64748b",
                fontSize: "0.85em",
              }}>
                <span className="loader" aria-hidden="true" />
                Ładowanie danych rozdziału…
              </div>
            ) : <>
            {informationSources.length > 0 && (
              <details open style={{
                background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
                padding: 10, marginTop: 12,
              }}>
                <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 600 }}>
                  📰 Pochodzenie ({informationSources.length})
                </summary>
                {informationSources.map(source => (
                  <div key={source.id} style={{ marginTop: 7 }}>
                    <div style={{ fontSize: "0.75em", color: "#64748b" }}>
                      {SOURCE_ROLE_LABELS[source.role] ?? source.role}
                    </div>
                    <NavLink to={`/information-sources?id=${source.source_id}`} style={{ color: "#0369a1", fontWeight: 600 }}>
                      {source.canonical_name}
                    </NavLink>
                    {source.source_url && <>{" "}<a href={source.source_url} target="_blank" rel="noreferrer" title="Otwórz publikację">↗</a></>}
                    {source.evidence_excerpt && (
                      <div style={{ fontSize: "0.76em", color: "#475569", marginTop: 2 }}>
                        „{source.evidence_excerpt}”
                      </div>
                    )}
                  </div>
                ))}
              </details>
            )}
            {citedPublications.length > 0 && (
              <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 10, marginTop: 12 }}>
                <strong style={{ fontSize: "0.85em", display: "block", marginBottom: 8 }}>📚 Cytowane publikacje</strong>
                {citedPublications.map(publication => {
                  const identifier = publication.pmid ? `PMID ${publication.pmid}`
                    : publication.pmcid ? publication.pmcid
                    : publication.doi ? `DOI ${publication.doi}` : "Publikacja";
                  return <div key={publication.id} style={{ marginTop: 7, fontSize: "0.8em" }}>
                    <a href={publication.canonical_url} target="_blank" rel="noreferrer" style={{ color: "#6d28d9", fontWeight: 600 }}>
                      {publication.title || identifier} ↗
                    </a>
                    {publication.title && <div style={{ color: "#64748b" }}>{identifier}</div>}
                  </div>;
                })}
              </div>
            )}
            {(shownCountries.length > 0 || shownMarkers.length > 0 || shownPipelines.length > 0) && (
              <React.Suspense fallback={null}>
                <CountryMap countries={shownCountries} places={shownMarkers} pipelines={shownPipelines} />
              </React.Suspense>
            )}

            {nerUnavailableAt && (
              <div style={{
                background: "#fff7ed", border: "1px solid #fdba74", borderRadius: 8,
                padding: 10, marginTop: 12, fontSize: "0.85em", color: "#9a3412",
              }}>
                ⚠️ Wykrywanie osób i miejsc nie powiodło się — serwis NER był niedostępny
                ({new Date(nerUnavailableAt).toLocaleString("pl-PL")}). Lista poniżej może być pusta lub niepełna,
                niekoniecznie dlatego, że w dokumencie nic nie ma. Spróbuj ponownej analizy w edytorze dokumentu.
              </div>
            )}

            {(shownPersons.length > 0 || shownPlaceItems.length > 0) && (
              <details open style={{
                background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
                padding: 10, marginTop: 12, fontSize: "0.9em",
              }}>
                <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 600 }}>
                  👤 Osoby i miejsca ({shownPersons.length + shownPlaceItems.length})
                </summary>
                <EntityChips label={"👤 Osoby"} items={shownPersons} linkPersons searchUnresolvedPersons
                  highlightMode={highlightMode} onHighlight={handleEntityHighlight} />
                <EntityChips label={"📍 Miejsca"} items={shownPlaceItems}
                  highlightMode={highlightMode} onHighlight={handleEntityHighlight} />
              </details>
            )}

            {scoped && !shownPersons.length && !shownPlaceItems.length
              && !shownCountries.length && !shownMarkers.length && (
              <div style={{ fontSize: "0.8em", color: "#94a3b8", marginTop: 8 }}>
                Brak osób i miejsc w tym rozdziale.
              </div>
            )}

            <TimePeriodsPanel docId={id} currentChapter={position} />

            <TonePanel docId={id} currentChapter={position} />

            <TimelinePanel docId={id} currentChapter={position} onEventClick={handleTimelineEventClick} />

            {thematicTags.length > 0 && (
              // A book can carry hundreds of miejsce-* tags — start collapsed
              // beyond a screenful so the tag wall doesn't swallow the panel.
              <details open={thematicTags.length <= TAGS_OPEN_THRESHOLD} style={{
                background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
                padding: 10, marginTop: 12,
              }}>
                <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 600 }}>
                  🏷️ Tagi ({thematicTags.length})
                </summary>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                  {thematicTags.map(tag => (
                    <span key={tag} style={{
                      fontSize: "0.78em", padding: "2px 8px", borderRadius: 999,
                      background: "#f1f5f9", color: "#334155",
                    }}>
                      {tag}
                    </span>
                  ))}
                </div>
              </details>
            )}

            {(content?.synthesis_chapter || synthesis) && (
              <details className={styles.synthesisPanel} open>
                <summary>📄 Streszczenie {content?.synthesis_chapter ? "rozdziału" : "dokumentu"}</summary>
                <div style={{ fontSize: "0.85em", lineHeight: 1.55, whiteSpace: "pre-wrap", marginTop: 8 }}>
                  {content?.synthesis_chapter ?? synthesis}
                </div>
              </details>
            )}
            </>}
          </div>
        )}
      </div>

      {/* Note popover */}
      {pendingNote && (
        <NotePopover pending={pendingNote} onSave={saveNote} onSearch={searchSelectedQuote}
          onCancel={() => setPendingNote(null)} />
      )}
    </div>
  );
};

export default Read;
