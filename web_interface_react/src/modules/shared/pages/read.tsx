import React from "react";
import { useParams, useSearchParams, NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import {
  NotePopover, NoteRow, PendingNote, ReaderIdentityBadge, STANCE_ICON, UserNote,
  normalizeWs, pendingNoteFromSelection, useReaderIdentity, useUserNotes,
} from "../components/ReaderNotes/readerNotes";
import type { CountryTag, PipelineLine, PlaceMarker } from "../components/CountryMap/countryMap";
import ContentGroupsPanel from "../components/ContentGroupsPanel/ContentGroupsPanel";
import EntitiesPanel, { EntityItem } from "../components/EntitiesPanel/entitiesPanel";
import TimelinePanel, { type EventItem } from "../components/TimelinePanel/timelinePanel";
import TimePeriodsPanel from "../components/TimePeriodsPanel/timePeriodsPanel";
import TonePanel from "../components/TonePanel/tonePanel";
import RelationshipGraph, { type RelationshipGraphData } from "../components/RelationshipGraph/relationshipGraph";
import { useIsDesktop } from "../hooks/useIsDesktop";
import { isOpenableSourceUrl, toOpenableSourceUrl } from "../utils/sourceUrl";
import ChapterGroupsPanel from "../components/ChapterGroupsPanel/ChapterGroupsPanel";
import { buildObsidianNoteUrl } from "../utils/obsidian";
import {
  loadReaderSidebarVisible, saveReaderSidebarVisible,
  loadReaderObsidianPanelVisible, saveReaderObsidianPanelVisible,
} from "../services/storage";
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

interface ListNeighbors {
  previous_id: number | null;
  next_id: number | null;
}

// Footnote extracted out of the book text (document_references) — rendered
// as a "Przypisy" section at the end of the chapter, linked from ¹⁸ markers.
interface ChapterReference {
  marker: string;
  text: string;
  url: string | null;
}

// Image extracted from an imported book PDF (document_images, storage_key-sourced)
// — "inline" tells the reader whether the image has a [imgN] marker in the
// chapter text (new imports) or needs to render in the chapter-end "Ilustracje"
// section instead (backfilled books, imported before extraction existed).
// "url" is a presigned MinIO link (null on a LocalStorage backend — placeholder).
interface ChapterImage {
  position: number | null;
  url: string | null;
  caption_text: string | null;
  alt_text: string | null;
  page_number: number | null;
  inline: boolean;
}

interface ChapterContent {
  position: number;
  title: string;
  text: string;
  chapter_total: number;
  references?: ChapterReference[];
  images?: ChapterImage[];
  // Obsidian [[Title]] wikilinks resolved to obsidian_note document ids —
  // computed fresh on every request (chunk_review_routes.py's
  // _resolve_wiki_links), keyed by lowercased target title. A target absent
  // from this map means "no single matching note" — rendered as plain text.
  wiki_links?: Record<string, number>;
  // Synthesis of a run analysed with this chapter as scope (GET /document/:id/chapter/:pos) —
  // takes priority over the whole-document synthesis from GET /document/:id/chapters.
  synthesis_chapter?: string | null;
  // Notes written from this chapter's DocumentChunk(s) via the /lenie-obsidian-note
  // skill — either a chapter-scoped analysis run's chunks (book chapters) or the
  // single TEMAT chunk this chapter maps to (transcript-chunk fallback chapters).
  // Distinct name from the document-level docObsidianNotePaths state below.
  chapter_obsidian_note_paths?: string[];
  prev: number | null;
  next: number | null;
}

interface ImportedObsidianNote {
  path: string;
  id: number;
  title: string;
  text: string;
  // Title (lowercased) -> obsidian_note document id, resolved server-side
  // against this note's own [[Title]] wikilinks (chunk_review_routes.py's
  // document_obsidian_notes) -- distinct from the viewed document's own
  // wikiLinksByTitle below.
  wiki_links?: Record<string, number>;
}

// Chapter-scoped sidebar data (GET /document/:id/chapter/:pos/entities) —
// document-level entities/countries filtered down to the chapter being read.
interface ChapterScope {
  persons: EntityItem[];
  organizations: EntityItem[];
  placeItems: EntityItem[];
  facilities: EntityItem[];
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
  review_status: string;
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

// ── Minimal markdown rendering (headings, paragraphs, hr, [imgN] figures) ────

// Raw markdown image syntax (web-article text) — still skipped entirely, distinct
// from our own [imgN] markers (book PDF images) handled by IMG_MARKER below.
const IMAGE_LINE = /^!\[[^\]]*\]\([^)]*\)$/;
const IMG_MARKER = /^\[img(\d+)\](?:\s+([\s\S]+))?$/;
// In-text jump target inserted by e.g. library.book_pdf_import._link_table_captions()
// before a book table's real occurrence — see ANCHOR_LINK in renderInline() for
// the clickable link that navigates here (GET /document/:id/anchor/:anchor_id).
const ANCHOR_MARKER = /^\[#([\w-]+)\]$/;
const ANCHOR_LINK = /\[([^\]]+)\]\(anchor:([\w-]+)\)/g;

/** Inline figure for a book-PDF image ([imgN] marker) or a chapter-end
 *  "Ilustracje" entry. url is null on a LocalStorage backend (no presigned
 *  links) — shows the caption alone rather than a broken image box. */
function renderChapterImage(img: ChapterImage, key: React.Key): React.ReactNode {
  const figureStyle: React.CSSProperties = { margin: "20px 0", textAlign: "center" };
  if (!img.url) {
    return img.caption_text ? (
      <figure key={key} style={figureStyle}>
        <figcaption style={{ fontSize: "0.8em", color: "#64748b" }}>{img.caption_text}</figcaption>
      </figure>
    ) : null;
  }
  return (
    <figure key={key} style={figureStyle}>
      <a href={img.url} target="_blank" rel="noreferrer">
        <img
          src={img.url}
          alt={img.alt_text ?? img.caption_text ?? ""}
          style={{ maxWidth: "100%", height: "auto", borderRadius: 4 }}
        />
      </a>
      {img.caption_text && (
        <figcaption style={{ fontSize: "0.8em", color: "#64748b", marginTop: 6 }}>{img.caption_text}</figcaption>
      )}
    </figure>
  );
}

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

function renderInline(
  text: string,
  refs?: Map<string, ChapterReference>,
  onAnchorClick?: (anchorId: string) => void,
  images?: Map<number, ChapterImage>,
  wikiLinks?: Map<string, number>,
  onWikiLinkClick?: (targetId: number) => void,
): React.ReactNode[] {
  // **bold**, *italic*, `code`, [label](anchor:id) jump links, ¹⁸ footnote
  // markers, a (https://...) URL — e.g. Gmail newsletter items flattened by
  // email_import.py's html_to_text() from <a href> into "label (url)" — and
  // an [imgN] marker sitting mid-sentence (Gmail decorative glyphs, e.g. a
  // 👋 emoji shipped as an <img> — IMG_MARKER in renderMarkdown only catches
  // a marker that is its own block) — enough for OCR-ed book prose. An
  // Obsidian [[Title]]/[[Title|Display]]/[[Title#Heading]] wikilink is
  // resolved against wikiLinks (GET /document/:id/chapter/:pos's wiki_links,
  // computed fresh server-side every request — see chunk_review_routes.py's
  // _resolve_wiki_links) rather than at import time, so a link to a note
  // created/renamed after this note was last imported still resolves.
  const parts = text.split(
    /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[\[[^\]]+\]\]|\[[^\]]+\]\(anchor:[\w-]+\)|\(https?:\/\/[^\s)]+\)|\[img\d+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+)/g,
  );
  return parts.map((part, i) => {
    const urlInParens = part.match(/^\((https?:\/\/[^\s)]+)\)$/);
    if (urlInParens) {
      const url = urlInParens[1];
      return (
        <React.Fragment key={i}>
          (<a href={url} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all", color: "#0369a1" }}>
            {url}
          </a>)
        </React.Fragment>
      );
    }
    const inlineImgMarker = part.match(/^\[img(\d+)\]$/);
    if (inlineImgMarker) {
      const img = images?.get(Number(inlineImgMarker[1]));
      if (!img?.url) return null;
      return (
        <a key={i} href={img.url} target="_blank" rel="noreferrer">
          <img
            src={img.url}
            alt={img.alt_text ?? img.caption_text ?? ""}
            style={{ height: "1.2em", verticalAlign: "middle", margin: "0 2px" }}
          />
        </a>
      );
    }
    const wikiLink = part.match(/^\[\[([^\]]+)\]\]$/);
    if (wikiLink) {
      const label = wikiLink[1].split("|", 2)[1] ?? wikiLink[1].split("#", 2)[0];
      const targetTitle = wikiLink[1].split("|", 1)[0].split("#", 1)[0].trim();
      const targetId = wikiLinks?.get(targetTitle.toLowerCase());
      if (targetId != null) {
        if (onWikiLinkClick) {
          return (
            <a
              key={i}
              href={`/read/${targetId}`}
              onClick={(e) => { e.preventDefault(); onWikiLinkClick(targetId); }}
              style={{ color: "#0369a1", textDecoration: "underline", cursor: "pointer" }}
            >
              {label}
            </a>
          );
        }
        return (
          <NavLink key={i} to={`/read/${targetId}`} style={{ color: "#0369a1", textDecoration: "underline" }}>
            {label}
          </NavLink>
        );
      }
      // No matching obsidian_note (not imported, wrong title, or ambiguous)
      // — show the label without Obsidian's [[ ]] syntax rather than either
      // a dead link or raw brackets, with a tooltip explaining why.
      return (
        <span key={i} title="Notatka nie została jeszcze zaimportowana do Lenie" style={{ color: "#94a3b8" }}>
          {label}
        </span>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={i} style={{
          background: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 4,
          padding: "1px 4px", fontSize: "0.9em", fontFamily: "monospace",
        }}>
          {part.slice(1, -1)}
        </code>
      );
    }
    const anchorLink = part.match(/^\[([^\]]+)\]\(anchor:([\w-]+)\)$/);
    if (anchorLink) {
      const [, label, anchorId] = anchorLink;
      return (
        <span
          key={i}
          onClick={() => onAnchorClick?.(anchorId)}
          style={{ color: "#0369a1", cursor: onAnchorClick ? "pointer" : undefined, textDecoration: "underline" }}
        >
          {label}
        </span>
      );
    }
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

// Surface forms of people, organizations and facilities that have a stored
// description, for the always-on
// "hover a mention in the text" tooltip — distinct from highlightTerms,
// which only lights up on an explicit chip click.
interface EntityDescriptions {
  terms: string[];
  descriptionByTerm: Map<string, string>; // key: term.toLowerCase()
}

function buildEntityDescriptions(
  persons: EntityItem[], organizations: EntityItem[], facilities: EntityItem[],
): EntityDescriptions {
  const terms: string[] = [];
  const descriptionByTerm = new Map<string, string>();
  const add = (item: EntityItem, description: string | null | undefined) => {
    if (!description) return;
    entityHighlightTerms(item).forEach(term => {
      terms.push(term);
      descriptionByTerm.set(term.toLowerCase(), description);
    });
  };
  persons.forEach(item => add(item, item.person_description));
  organizations.forEach(item => add(item, item.organization_description));
  facilities.forEach(item => add(
    item,
    item.facility_description
      ? [item.facility_description, item.operator_name && `Operator: ${item.operator_name}`]
          .filter(Boolean)
          .join(" ")
      : undefined,
  ));
  return { terms, descriptionByTerm };
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
  onAnchorClick?: (anchorId: string) => void,
  images?: Map<number, ChapterImage>,
  wikiLinks?: Map<string, number>,
  described?: EntityDescriptions,
  onWikiLinkClick?: (targetId: number) => void,
): { nodes: React.ReactNode[]; paragraphTint: UserNote | null; timelineTint: boolean; timelineFound: boolean } {
  type Match = { idx: number; len: number; kind: "note" | "entity" | "timeline" | "described"; note?: UserNote; description?: string };
  const noteMatches: Match[] = notes
    .map(n => ({ note: n, idx: text.indexOf(n.anchor_quote), len: n.anchor_quote.length, kind: "note" as const }))
    .filter(m => m.idx >= 0);
  const entityMatches: Match[] = findEntityMatches(text, highlightTerms ?? [])
    .map(m => ({ ...m, kind: "entity" as const }));
  const describedMatches: Match[] = described
    ? findEntityMatches(text, described.terms).map(m => ({
        ...m, kind: "described" as const,
        description: described.descriptionByTerm.get(text.slice(m.idx, m.idx + m.len).toLowerCase()),
      })).filter(m => m.description)
    : [];
  const timelineIndex = timelineAnchor ? text.indexOf(timelineAnchor) : -1;
  const timelineMatches: Match[] = timelineAnchor && timelineIndex >= 0
    ? [{ idx: timelineIndex, len: timelineAnchor.length, kind: "timeline" }]
    : [];
  const matches = [...timelineMatches, ...noteMatches, ...entityMatches, ...describedMatches].sort((a, b) => a.idx - b.idx);
  const paragraphTint = notes.find(n =>
    text.indexOf(n.anchor_quote) < 0
    && normalizeAnchorText(text).includes(normalizeAnchorText(n.anchor_quote))) ?? null;
  const timelineTint = Boolean(
    timelineAnchor && timelineIndex < 0
    && normalizeAnchorText(text).includes(normalizeAnchorText(timelineAnchor)),
  );
  const timelineFound = timelineIndex >= 0 || timelineTint;

  if (matches.length === 0) {
    return {
      nodes: renderInline(text, refs, onAnchorClick, images, wikiLinks, onWikiLinkClick),
      paragraphTint, timelineTint, timelineFound,
    };
  }

  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  matches.forEach((m, i) => {
    if (m.idx < cursor) return; // overlapping match — skip
    if (m.idx > cursor) {
      nodes.push(...renderInline(text.slice(cursor, m.idx), refs, onAnchorClick, images, wikiLinks, onWikiLinkClick));
    }
    const quoted = text.slice(m.idx, m.idx + m.len);
    if (m.kind === "note" && m.note) {
      nodes.push(
        <mark
          key={`note-${m.note.id}-${i}`}
          title={`${STANCE_ICON[m.note.stance ?? ""] ?? "📝"} ${m.note.note_text}`}
          style={{ background: "#fef08a", padding: "0 1px", cursor: "help" }}
        >
          {renderInline(quoted, refs, onAnchorClick, images, wikiLinks, onWikiLinkClick)}
        </mark>
      );
    } else if (m.kind === "timeline") {
      nodes.push(
        <mark
          key={`timeline-${i}`}
          className="timeline-highlight"
          style={{ background: "#fed7aa", padding: "0 1px" }}
        >
          {renderInline(quoted, refs, onAnchorClick, images, wikiLinks, onWikiLinkClick)}
        </mark>
      );
    } else if (m.kind === "described") {
      nodes.push(
        <span
          key={`desc-${i}`}
          title={m.description}
          style={{ borderBottom: "1px dotted #64748b", cursor: "help" }}
        >
          {renderInline(quoted, refs, onAnchorClick, images, wikiLinks, onWikiLinkClick)}
        </span>
      );
    } else {
      nodes.push(
        <mark
          key={`ent-${i}`}
          className="entity-highlight"
          style={{ background: "#bfdbfe", padding: "0 1px" }}
        >
          {renderInline(quoted, refs, onAnchorClick, images, wikiLinks, onWikiLinkClick)}
        </mark>
      );
    }
    cursor = m.idx + m.len;
  });
  if (cursor < text.length) {
    nodes.push(...renderInline(text.slice(cursor), refs, onAnchorClick, images, wikiLinks, onWikiLinkClick));
  }
  return { nodes, paragraphTint, timelineTint, timelineFound };
}

const CALLOUT_RE = /^\[!(INFO|WARN)\]\n([\s\S]*?)\n\[!\/\1\]$/;
const TABLE_SEPARATOR_RE = /^\|(\s*:?-{2,}:?\s*\|)+$/;

// A fenced code block (```lang\n...\n```) must open/close on its own line —
// anchored per-line via the "m" flag rather than requiring the whole text to
// start/end with it, so a fence can sit anywhere in the chapter. Matched and
// pulled out BEFORE the blank-line block split below, because real code
// commonly contains blank lines that would otherwise fragment it into
// several unrelated "paragraphs".
const CODE_FENCE_RE = /^```[ \t]*([\w+-]*)[ \t]*\r?\n([\s\S]*?)\r?\n```[ \t]*$/gm;

interface TextSegment { code: false; content: string }
interface CodeSegment { code: true; lang: string; content: string }

function splitCodeFences(text: string): (TextSegment | CodeSegment)[] {
  const segments: (TextSegment | CodeSegment)[] = [];
  let lastIndex = 0;
  CODE_FENCE_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = CODE_FENCE_RE.exec(text))) {
    if (match.index > lastIndex) segments.push({ code: false, content: text.slice(lastIndex, match.index) });
    segments.push({ code: true, lang: match[1] ?? "", content: match[2] });
    lastIndex = CODE_FENCE_RE.lastIndex;
  }
  if (lastIndex < text.length) segments.push({ code: false, content: text.slice(lastIndex) });
  return segments;
}

/** Verbatim block — no inline markdown/entity/note processing, matching how
 *  every other markdown renderer treats a fenced code block's contents. */
function renderCodeBlock(seg: CodeSegment, key: React.Key): React.ReactNode {
  return (
    <div key={key} style={{ position: "relative", margin: "16px 0" }}>
      {seg.lang && (
        <span style={{
          position: "absolute", top: 6, right: 10, fontSize: "0.72em",
          color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.04em",
        }}>
          {seg.lang}
        </span>
      )}
      <pre style={{
        background: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 8,
        padding: "14px 16px", overflowX: "auto", margin: 0,
        fontSize: "0.85em", lineHeight: 1.5,
      }}>
        <code style={{ fontFamily: "monospace", whiteSpace: "pre" }}>{seg.content}</code>
      </pre>
    </div>
  );
}

function parseTableRow(line: string): string[] {
  const inner = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return inner.split(/(?<!\\)\|/).map(cell => cell.trim().replace(/\\\|/g, "|"));
}

function renderTableBlock(
  trimmed: string,
  key: React.Key,
  notes: UserNote[],
  refs?: Map<string, ChapterReference>,
  highlightTerms?: string[],
  timelineAnchor?: string | null,
  onAnchorClick?: (anchorId: string) => void,
  images?: Map<number, ChapterImage>,
  wikiLinks?: Map<string, number>,
  described?: EntityDescriptions,
  onWikiLinkClick?: (targetId: number) => void,
): React.ReactNode | null {
  const lines = trimmed.split("\n");
  if (lines.length < 2 || !lines[0].trim().startsWith("|") || !TABLE_SEPARATOR_RE.test(lines[1].trim())) return null;
  const header = parseTableRow(lines[0]);
  const rows = lines.slice(2).map(parseTableRow);
  const cell = (text: string) => renderParagraphWithNotes(
    text, notes, refs, highlightTerms, timelineAnchor, onAnchorClick, images, wikiLinks, described, onWikiLinkClick,
  ).nodes;
  return (
    <div key={key} style={{ overflowX: "auto", margin: "16px 0" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.88em" }}>
        <thead>
          <tr>
            {header.map((h, hi) => (
              <th key={hi} style={{
                border: "1px solid #e2e8f0", padding: "6px 10px", background: "#f8fafc",
                textAlign: "left", verticalAlign: "top",
              }}>
                {cell(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((c, ci) => (
                <td key={ci} style={{ border: "1px solid #e2e8f0", padding: "6px 10px", verticalAlign: "top" }}>
                  {cell(c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const LIST_LINE_RE = /^\s*([-*]|\d+\.)\s+(.*)$/;

/** Unordered (`-`/`*`) or ordered (`1.`) markdown list — every line in the
 *  block must match, otherwise this isn't a list block (e.g. a "---" rule or
 *  a single dash inside prose). Flat rendering only — nesting by indentation
 *  isn't tracked, list items just render as sibling <li>s. */
function renderListBlock(
  trimmed: string,
  key: React.Key,
  notes: UserNote[],
  refs?: Map<string, ChapterReference>,
  highlightTerms?: string[],
  timelineAnchor?: string | null,
  onAnchorClick?: (anchorId: string) => void,
  images?: Map<number, ChapterImage>,
  wikiLinks?: Map<string, number>,
  described?: EntityDescriptions,
  onWikiLinkClick?: (targetId: number) => void,
): React.ReactNode | null {
  const lines = trimmed.split("\n").filter(l => l.trim());
  if (lines.length === 0 || !lines.every(line => LIST_LINE_RE.test(line))) return null;
  const ordered = /^\s*\d+\./.test(lines[0]);
  const Tag = ordered ? "ol" : "ul";
  return (
    <Tag key={key} style={{ margin: "10px 0", paddingLeft: 24, lineHeight: 1.65 }}>
      {lines.map((line, li) => {
        const itemText = line.match(LIST_LINE_RE)![2];
        const { nodes } = renderParagraphWithNotes(
          itemText, notes, refs, highlightTerms, timelineAnchor, onAnchorClick, images, wikiLinks, described,
          onWikiLinkClick,
        );
        return <li key={li}>{nodes}</li>;
      })}
    </Tag>
  );
}

function renderCalloutBlock(
  trimmed: string,
  key: React.Key,
  notes: UserNote[],
  refs?: Map<string, ChapterReference>,
  highlightTerms?: string[],
  timelineAnchor?: string | null,
  onAnchorClick?: (anchorId: string) => void,
  images?: Map<number, ChapterImage>,
  wikiLinks?: Map<string, number>,
  described?: EntityDescriptions,
  onWikiLinkClick?: (targetId: number) => void,
): React.ReactNode | null {
  const match = trimmed.match(CALLOUT_RE);
  if (!match) return null;
  const isWarn = match[1] === "WARN";
  const { nodes } = renderParagraphWithNotes(
    match[2].replace(/\n/g, " "), notes, refs, highlightTerms, timelineAnchor,
    onAnchorClick, images, wikiLinks, described, onWikiLinkClick,
  );
  return (
    <div key={key} style={{
      display: "flex", gap: 8, alignItems: "flex-start",
      background: isWarn ? "#fef2f2" : "#f0fdf4",
      border: `1px solid ${isWarn ? "#fecaca" : "#bbf7d0"}`,
      borderLeft: `4px solid ${isWarn ? "#dc2626" : "#16a34a"}`,
      borderRadius: 8, padding: "10px 14px", margin: "16px 0", lineHeight: 1.6,
    }}>
      <span aria-hidden="true">{isWarn ? "⚠️" : "ℹ️"}</span>
      <div>{nodes}</div>
    </div>
  );
}

function renderMarkdown(
  text: string,
  notes: UserNote[],
  refs?: Map<string, ChapterReference>,
  highlightTerms?: string[],
  timelineAnchor?: string | null,
  images?: Map<number, ChapterImage>,
  onAnchorClick?: (anchorId: string) => void,
  wikiLinks?: Map<string, number>,
  described?: EntityDescriptions,
  onWikiLinkClick?: (targetId: number) => void,
): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  splitCodeFences(text).forEach((segment, segIndex) => {
    if (segment.code) {
      out.push(renderCodeBlock(segment, `code-${segIndex}`));
      return;
    }
    const blocks = segment.content.split(/\n\s*\n/);
    blocks.forEach((block, i) => {
      const key = `${segIndex}-${i}`;
      const trimmed = block.trim();
      if (!trimmed) return;
      const markerMatch = trimmed.match(IMG_MARKER);
      if (markerMatch) {
        const img = images?.get(Number(markerMatch[1]));
        if (img) out.push(renderChapterImage(img, key));
        // Gmail can place an image marker directly beside a CTA, e.g.
        // "[img4] Pobierz". Preserve the CTA rather than leaving the marker as
        // visible text or discarding the whole line.
        const trailingText = markerMatch[2]?.trim();
        if (trailingText) {
          const { nodes, paragraphTint, timelineTint, timelineFound } = renderParagraphWithNotes(
            trailingText, notes, refs, highlightTerms, timelineAnchor, onAnchorClick, images, wikiLinks, described,
            onWikiLinkClick,
          );
          out.push(
            <p key={`${key}-trailing`} className={timelineFound ? "timeline-anchor-paragraph" : undefined} style={{
              lineHeight: 1.65, margin: "14px 0", textAlign: "justify",
              ...(paragraphTint ? { background: "#fefce8", borderLeft: "3px solid #eab308", paddingLeft: 8 } : {}),
              ...(timelineTint ? { background: "#fff7ed", borderLeft: "3px solid #f59e0b", paddingLeft: 8 } : {}),
            }}>
              {nodes}
            </p>,
          );
        }
        return;
      }
      const anchorMatch = trimmed.match(ANCHOR_MARKER);
      if (anchorMatch) {
        out.push(<span key={key} id={anchorMatch[1]} />);
        return;
      }
      if (IMAGE_LINE.test(trimmed)) return;
      const callout = renderCalloutBlock(
        trimmed, key, notes, refs, highlightTerms, timelineAnchor, onAnchorClick, images, wikiLinks, described,
        onWikiLinkClick,
      );
      if (callout) {
        out.push(callout);
        return;
      }
      const table = renderTableBlock(
        trimmed, key, notes, refs, highlightTerms, timelineAnchor, onAnchorClick, images, wikiLinks, described,
        onWikiLinkClick,
      );
      if (table) {
        out.push(table);
        return;
      }
      const list = renderListBlock(
        trimmed, key, notes, refs, highlightTerms, timelineAnchor, onAnchorClick, images, wikiLinks, described,
        onWikiLinkClick,
      );
      if (list) {
        out.push(list);
        return;
      }
      const heading = trimmed.match(/^(#{1,6})\s+(.*)$/s);
      if (heading) {
        const level = Math.min(heading[1].length + 1, 6);
        const Tag = `h${level}` as keyof JSX.IntrinsicElements;
        // headings can carry note anchors too (e.g. a quote of the chapter title)
        const { nodes, timelineTint, timelineFound } = renderParagraphWithNotes(
          heading[2].replace(/\n/g, " "), notes, undefined, highlightTerms, timelineAnchor,
          undefined, undefined, wikiLinks, undefined, onWikiLinkClick,
        );
        out.push(
          <Tag
            key={key}
            className={timelineFound ? "timeline-anchor-paragraph" : undefined}
            style={{ marginTop: level === 2 ? 0 : 28, ...(timelineTint ? { background: "#fff7ed" } : {}) }}
          >
            {nodes}
          </Tag>,
        );
        return;
      }
      if (trimmed === "---") {
        out.push(<hr key={key} style={{ margin: "20px 0", border: "none", borderTop: "1px solid #e2e8f0" }} />);
        return;
      }
      // footnote / caption lines (superscript digits or "Wykres N.") — smaller font
      const isNote = /^([¹²³⁴⁵⁶⁷⁸⁹⁰]+|\d{1,3} )\S*\s*(http|www|[A-ZŻŹĆĄŚĘŁÓŃ])/.test(trimmed) && trimmed.length < 400;
      const paraText = trimmed.replace(/\n/g, " ");
      const { nodes, paragraphTint, timelineTint, timelineFound } = renderParagraphWithNotes(
        paraText, notes, refs, highlightTerms, timelineAnchor, onAnchorClick, images, wikiLinks, described,
        onWikiLinkClick,
      );
      out.push(
        <p key={key} className={timelineFound ? "timeline-anchor-paragraph" : undefined} style={isNote
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
  });
  return out;
}

// Document types that have an editor page at /{type}/:id
const EDITOR_TYPES = new Set(["webpage", "link", "youtube", "movie", "email"]);

// Tag counts above this render the sidebar "Tagi" section collapsed by default.
const TAGS_OPEN_THRESHOLD = 20;

// Above this many chapters, "all chapters" view is hidden — it fetches every
// chapter's content up front, which stops being a reasonable trade-off for
// long books.
const ALL_CHAPTERS_VIEW_MAX = 30;

// ── Page ─────────────────────────────────────────────────────────────────────

const Read: React.FC = () => {
  const { id } = useParams();
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();

  const [chapters, setChapters] = React.useState<Chapter[]>([]);
  const [readerCompact, setReaderCompact] = React.useState(false);
  const [documentType, setDocumentType] = React.useState<string | null>(null);
  const [docTitle, setDocTitle] = React.useState<string | null>(null);
  const [countries, setCountries] = React.useState<CountryTag[]>([]);
  const [places, setPlaces] = React.useState<PlaceMarker[]>([]);
  const [personItems, setPersonItems] = React.useState<EntityItem[]>([]);
  const [organizationItems, setOrganizationItems] = React.useState<EntityItem[]>([]);
  const [placeItems, setPlaceItems] = React.useState<EntityItem[]>([]);
  const [facilityItems, setFacilityItems] = React.useState<EntityItem[]>([]);
  // Set when the last NER refresh found ner_service unreachable (backend:
  // web_documents.ner_unavailable_at) — distinguishes "service was down" from
  // "genuinely no persons/places in this document" so the reader can warn
  // instead of just staying silently empty.
  const [nerUnavailableAt, setNerUnavailableAt] = React.useState<string | null>(null);
  // null until refresh_document_entities has successfully run at least once
  // for this document (backend: documents.entities_checked_at) — tells apart
  // "never analyzed" from "analyzed, genuinely no persons/places/organizations".
  const [entitiesCheckedAt, setEntitiesCheckedAt] = React.useState<string | null>(null);
  // Bumped after an edit made via the "Edytuj encje" panel (EntitiesPanel,
  // rendered below) so the chapter-scoped effect refetches too — it's keyed
  // on [position, scopeChapter, ...], not on document_entities changing.
  const [entitiesEditVersion, setEntitiesEditVersion] = React.useState(0);
  const [thematicTags, setThematicTags] = React.useState<string[]>([]);
  const [synthesis, setSynthesis] = React.useState<string | null>(null);
  const [informationSources, setInformationSources] = React.useState<InformationSourceLink[]>([]);
  const [citedPublications, setCitedPublications] = React.useState<CitedPublicationLink[]>([]);
  const [relationshipGraph, setRelationshipGraph] = React.useState<RelationshipGraphData | null>(null);
  const [docQuality, setDocQuality] = React.useState<DocQuality | null>(null);
  const [docUrl, setDocUrl] = React.useState<string | null>(null);
  const [docPublishedOn, setDocPublishedOn] = React.useState<string | null>(null);
  const [docIngestedAt, setDocIngestedAt] = React.useState<string | null>(null);
  const [docObsidianNotePaths, setDocObsidianNotePaths] = React.useState<string[]>([]);
  const [content, setContent] = React.useState<ChapterContent | null>(null);
  const [importedObsidianNotes, setImportedObsidianNotes] = React.useState<ImportedObsidianNote[]>([]);
  const [selectedObsidianNotePath, setSelectedObsidianNotePath] = React.useState<string | null>(null);
  const [obsidianNotesLoading, setObsidianNotesLoading] = React.useState(false);
  const [obsidianPanelVisible, setObsidianPanelVisible] = React.useState(loadReaderObsidianPanelVisible);
  // In-panel browsing of the imported Obsidian vault, independent of the
  // article shown on the left — following a [[wikilink]] (or switching to
  // another note) inside the panel pushes the previously shown note onto
  // this stack and fetches the target by id (GET /document/:id/obsidian_note)
  // instead of navigating the reader's own /read/:id route.
  const [obsidianBrowseNote, setObsidianBrowseNote] = React.useState<ImportedObsidianNote | null>(null);
  const [obsidianBrowseHistory, setObsidianBrowseHistory] = React.useState<ImportedObsidianNote[]>([]);
  const [obsidianBrowseLoading, setObsidianBrowseLoading] = React.useState(false);
  // "all chapters" view: render every chapter's content on one page instead of
  // paging through them one at a time — fetched on demand (not on every load),
  // since it means one request per chapter.
  const [chapterViewAll, setChapterViewAll] = React.useState(false);
  const [allChapters, setAllChapters] = React.useState<ChapterContent[] | null>(null);
  const [allChaptersLoading, setAllChaptersLoading] = React.useState(false);
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
  // The navigation/notes column is useful, but takes substantial horizontal
  // space beside the text. Keep it open initially, with an explicit desktop
  // control to collapse the entire column when it is not needed.
  const [readerSidebarVisible, setReaderSidebarVisible] = React.useState(loadReaderSidebarVisible);
  // Set by an in-text anchor link (e.g. a "Spis tabel" entry) click — the
  // target anchor id to scroll to once the (possibly different) chapter it
  // resolved to has finished loading. See handleAnchorClick() and the effect
  // scrolling to it below, modeled on the timelineHighlight effect.
  const [pendingAnchorScroll, setPendingAnchorScroll] = React.useState<string | null>(null);
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
  const approveInformationSource = async (source: InformationSourceLink) => {
    const response = await fetch(`${apiUrl}/document/${id}/information_sources/${source.id}/approve`, {
      method: "POST", headers: jsonHeaders,
    });
    if (!response.ok) return;
    setInformationSources(items => items.map(item => item.id === source.id ? { ...item, review_status: "approved" } : item));
  };
  const { notes, createNote, saveNoteText, deleteNote } = useUserNotes(apiUrl, id, identity);
  const [pendingNote, setPendingNote] = React.useState<PendingNote | null>(null);
  const [tagQuery, setTagQuery] = React.useState("");
  const [tagResults, setTagResults] = React.useState<UserNote[]>([]);
  const hasReaderSidebar = chapters.length > 1 || Boolean(userId);
  const hasObsidianPanel = obsidianNotesLoading || importedObsidianNotes.length > 0;

  React.useEffect(() => { saveReaderSidebarVisible(readerSidebarVisible); }, [readerSidebarVisible]);
  React.useEffect(() => { saveReaderObsidianPanelVisible(obsidianPanelVisible); }, [obsidianPanelVisible]);

  const requestedPosition = Number(searchParams.get("chapter") ?? 1);
  const position = readerCompact ? 1 : requestedPosition;
  const listContext = searchParams.get("list") ?? "";
  const listReaderSearch = listContext ? `?list=${encodeURIComponent(listContext)}` : "";
  const [listNeighbors, setListNeighbors] = React.useState<ListNeighbors | null>(null);

  React.useEffect(() => {
    if (!listContext) { setListNeighbors(null); return; }
    const params = new URLSearchParams(listContext);
    params.set("document_id", id ?? "");
    void fetch(`${apiUrl}/website_list_neighbors?${params.toString()}`, { headers })
      .then(response => response.ok ? response.json() : null)
      .then(data => setListNeighbors(data?.status === "success" ? data : null))
      .catch(() => setListNeighbors(null));
  }, [apiUrl, headers, id, listContext]);

  // ── Data loading ──

  React.useEffect(() => {
    // Clear the previous document's header/metadata up front — id just
    // changed, so none of this is valid for the new document yet. Without
    // this, a fetch failure below (e.g. a document too short for chapter
    // detection) left the prior document's title/url/ingested-date on
    // screen under the new id, reading as if the wrong document had loaded.
    setChapters([]);
    setDocumentType(null);
    setDocTitle(null);
    setCountries([]);
    setThematicTags([]);
    setSynthesis(null);
    setDocQuality(null);
    setDocUrl(null);
    setDocPublishedOn(null);
    setDocIngestedAt(null);
    setDocObsidianNotePaths([]);
    setImportedObsidianNotes([]);
    setSelectedObsidianNotePath(null);
    setError(null);
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
        setDocTitle(data.title ?? null);
        setCountries(data.countries ?? []);
        setThematicTags(data.thematic_tags ?? []);
        setSynthesis(data.synthesis ?? null);
        setDocQuality(data.quality ?? null);
        setDocUrl(data.url ?? null);
        setDocPublishedOn(data.published_on ?? null);
        setDocIngestedAt(data.ingested_at ?? null);
        setDocObsidianNotePaths(data.obsidian_note_paths ?? []);
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
    setRelationshipGraph(null);
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/document/${id}/relationship_graph`, { headers });
        const data = await response.json();
        if (data.status === "success") setRelationshipGraph({ nodes: data.nodes ?? [], edges: data.edges ?? [] });
      } catch { /* The graph is optional reader enrichment. */ }
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
  const fetchEntities = React.useCallback(async () => {
    try {
      const r = await fetch(`${apiUrl}/website_entities?id=${id}`, { headers });
      const data = await r.json();
      if (data.status !== "success") return;
      const items = [...(data.entities?.geogName ?? []), ...(data.entities?.placeName ?? [])];
      setPersonItems(data.entities?.persName ?? []);
      setOrganizationItems(data.entities?.orgName ?? []);
      setPlaceItems(items);
      setFacilityItems(data.entities?.facility ?? []);
      setNerUnavailableAt(data.ner_unavailable_at ?? null);
      setEntitiesCheckedAt(data.entities_checked_at ?? null);
      setPlaces(
        items
          .filter((it: any) => it.verified === true && it.lat != null && it.lon != null)
          .map((it: any) => ({ name: it.text, lat: it.lat, lon: it.lon })),
      );
    } catch {
      // encje są ozdobnikiem widoku — brak nie blokuje czytnika
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, apiKey]);

  React.useEffect(() => {
    fetchEntities();
  }, [fetchEntities]);

  // "Edytuj encje" panel (EntitiesPanel) changed something — refetch both the
  // document-level and (if in scope) the chapter-scoped sidebar data.
  const handleEntitiesEdited = React.useCallback(() => {
    fetchEntities();
    setEntitiesEditVersion((v) => v + 1);
  }, [fetchEntities]);

  // chapter-scoped sidebar data — refetched when the reader moves to another
  // chapter; a failure falls back to the document-level entities (scope null)
  React.useEffect(() => {
    if (!scopeChapter || !progressLoaded || chapterViewAll) {
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
          organizations: data.entities?.orgName ?? [],
          placeItems: items,
          facilities: data.entities?.facility ?? [],
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
  }, [apiUrl, id, position, scopeChapter, progressLoaded, apiKey, entitiesEditVersion, chapterViewAll]);

  // Resolve a raw ?highlight= mention to the variants that actually occur in
  // the loaded chapter. This keeps arrivals from the persons page aligned with
  // the same exact-token matching used by chapter-scoped sidebar clicks.
  React.useEffect(() => {
    const requested = searchParams.get("highlight")?.trim().toLowerCase();
    if (!requested || !chapterScope) return;
    const items = [
      ...chapterScope.persons,
      ...chapterScope.organizations,
      ...chapterScope.placeItems,
    ];
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
        if (requestId === contentRequestId.current) {
          // Otherwise the previous chapter's rendered text stays on screen
          // under the new error message, reading as if it belonged to the
          // document/chapter that just failed to load.
          setContent(null);
          setError(String(e));
        }
      } finally {
        if (requestId === contentRequestId.current) setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, position, progressLoaded, apiKey]);

  // "All chapters" view — fetches every chapter's content up front (one
  // request each) so they can all render on the same page. Only runs while
  // the toggle is on; switching it off just stops rendering this list, it
  // doesn't discard it, so re-enabling within the same document is instant.
  React.useEffect(() => {
    if (!chapterViewAll || chapters.length === 0) return;
    let cancelled = false;
    setAllChaptersLoading(true);
    (async () => {
      try {
        const results = await Promise.all(
          chapters.map(ch =>
            fetch(`${apiUrl}/document/${id}/chapter/${ch.position}?reader=1`, { headers })
              .then(r => r.json())
              .catch(() => null),
          ),
        );
        if (cancelled) return;
        setAllChapters(
          results.filter((d): d is ChapterContent & { status: string } => d?.status === "success"),
        );
      } finally {
        if (!cancelled) setAllChaptersLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterViewAll, chapters, apiUrl, id, apiKey]);

  // Notes generated from the article are reimported as regular Lenie documents.
  // Load their imported content for the reader's right-side preview, rather than
  // relying on an obsidian:// link that only works on a machine with Obsidian.
  React.useEffect(() => {
    if (!id || !content) return;
    let cancelled = false;
    setObsidianNotesLoading(true);
    // Moving to a different chapter/document invalidates any note reached by
    // browsing wikilinks from the previous chapter's panel.
    setObsidianBrowseNote(null);
    setObsidianBrowseHistory([]);
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/obsidian_notes?chapter=${position}`, { headers });
        const data = await r.json();
        if (cancelled || data.status !== "success") return;
        const notes = data.notes ?? [];
        setImportedObsidianNotes(notes);
        setSelectedObsidianNotePath(current =>
          notes.some((note: ImportedObsidianNote) => note.path === current) ? current : (notes[0]?.path ?? null),
        );
      } catch {
        if (!cancelled) setImportedObsidianNotes([]);
      } finally {
        if (!cancelled) setObsidianNotesLoading(false);
      }
    })();
    return () => { cancelled = true; };
    // headers is derived from reader identity; apiKey is its stable input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, apiKey, id, position, content]);

  const selectedObsidianNote = importedObsidianNotes.find(note => note.path === selectedObsidianNotePath) ?? null;
  // The note actually shown in the panel: whatever browsing landed on, or
  // (with an empty browse stack) the chapter-linked note picked above.
  const displayedObsidianNote = obsidianBrowseNote ?? selectedObsidianNote;

  const openObsidianNoteInPanel = React.useCallback(async (targetId: number) => {
    if (displayedObsidianNote) {
      setObsidianBrowseHistory(history => [...history, displayedObsidianNote]);
    }
    setObsidianBrowseLoading(true);
    try {
      const r = await fetch(`${apiUrl}/document/${targetId}/obsidian_note`, { headers });
      const data = await r.json();
      if (data.status === "success" && data.note) setObsidianBrowseNote(data.note);
    } catch {
      // in-panel wikilink browsing is best-effort — a failed hop just stays put
    } finally {
      setObsidianBrowseLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, headers, displayedObsidianNote]);

  const goBackObsidianBrowse = () => {
    setObsidianBrowseHistory(history => {
      if (history.length === 0) {
        setObsidianBrowseNote(null);
        return history;
      }
      setObsidianBrowseNote(history[history.length - 1]);
      return history.slice(0, -1);
    });
  };

  const resetObsidianBrowse = () => {
    setObsidianBrowseNote(null);
    setObsidianBrowseHistory([]);
  };

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

  // Scroll to an in-text anchor (e.g. a book table) after handleAnchorClick()
  // navigated to the chapter it lives in and that chapter's content loaded.
  React.useEffect(() => {
    if (!pendingAnchorScroll || !content) return;
    const t = window.setTimeout(() => {
      const el = contentRef.current?.querySelector<HTMLElement>(`#${CSS.escape(pendingAnchorScroll)}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      setPendingAnchorScroll(null);
    }, 300);
    return () => window.clearTimeout(t);
  }, [content, pendingAnchorScroll]);

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

  // TOC chapter click — in "all chapters" view every chapter is already on
  // the page, so jump there by scrolling instead of re-fetching a single one.
  const goToChapter = (pos: number | null) => {
    if (pos == null) return;
    if (chapterViewAll) {
      document.getElementById(`chapter-${pos}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      setTocOpen(false);
      return;
    }
    goTo(pos);
  };

  // In-text anchor link click (e.g. a "Spis tabel" entry) — resolve which
  // chapter the anchor currently falls in (computed fresh server-side, not
  // trusted from a number baked into the link) and jump there.
  const handleAnchorClick = async (anchorId: string) => {
    try {
      const r = await fetch(`${apiUrl}/document/${id}/anchor/${anchorId}?reader=1`, { headers });
      const data = await r.json();
      if (data.status !== "success") return;
      setPendingAnchorScroll(anchorId);
      goTo(data.position);
    } catch {
      // nothing to jump to — leave the link inert
    }
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

  // book-PDF images by marker position — for [imgN] inline rendering
  const imagesByPosition = React.useMemo(
    () => new Map(
      (content?.images ?? [])
        .filter((img): img is ChapterImage & { position: number } => img.position !== null)
        .map(img => [img.position, img]),
    ),
    [content?.images]);

  // Obsidian [[Title]] wikilinks resolved by the backend for this chapter —
  // rebuilt from content.wiki_links (a plain object over the wire) each time
  // the chapter changes.
  const wikiLinksByTitle = React.useMemo(
    () => new Map(Object.entries(content?.wiki_links ?? {})),
    [content?.wiki_links]);

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
  const shownOrganizations = scoped ? scoped.organizations : organizationItems;
  const shownFacilities = scoped ? scoped.facilities : facilityItems;
  // Surface forms with a stored profile are rendered as a dotted-underline
  // hover tooltip directly on the chapter text.
  const entityDescriptions = React.useMemo(
    () => buildEntityDescriptions(shownPersons, shownOrganizations, shownFacilities),
    [shownPersons, shownOrganizations, shownFacilities],
  );
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

  const navButtons = content && content.chapter_total > 1 && !chapterViewAll && (
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
      onHeaderClick={n.chapter_position ? () => goToChapter(readerCompact ? 1 : n.chapter_position) : undefined}
      onSaveText={saveNoteText}
      onDelete={deleteNote}
    />
  );

  return (
    <div>
      <NavLink to={`/entities/${id}`} style={{ float: "right", fontSize: "0.85em", color: "#0369a1" }}>
        Encje (NER)
      </NavLink>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }} title={docTitle ?? undefined}>
          {docTitle ? docTitle : `Czytelnik — dokument #${id}`}
        </h2>
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
        {hasReaderSidebar && (
          <button
            className={styles.sidebarToggleButton}
            type="button"
            onClick={() => setReaderSidebarVisible(visible => !visible)}
            aria-controls="reader-sidebar"
            aria-expanded={readerSidebarVisible}
          >
            {readerSidebarVisible ? "◀ Ukryj panel" : "▶ Pokaż panel"}
          </button>
        )}
        {isDesktop && hasObsidianPanel && (
          <button
            className={styles.sidebarToggleButton}
            type="button"
            onClick={() => setObsidianPanelVisible(visible => !visible)}
            aria-controls="obsidian-panel"
            aria-expanded={obsidianPanelVisible}
          >
            {obsidianPanelVisible ? "◀ Ukryj notatkę" : "▶ Pokaż notatkę"}
          </button>
        )}
        {hasReaderSidebar && (
          <button className={styles.tocToggleButton} onClick={() => setTocOpen(o => !o)}>
            📑 Panel czytnika{chapters.length > 1 ? ` (${chapters.length})` : ""}
          </button>
        )}
        {!readerCompact && chapters.length > 1 && chapters.length <= ALL_CHAPTERS_VIEW_MAX && (
          <button
            className={styles.sidebarToggleButton}
            type="button"
            onClick={() => setChapterViewAll(v => !v)}
            title={chapterViewAll
              ? "Wróć do przeglądania jednego rozdziału naraz"
              : "Pokaż wszystkie rozdziały na jednej stronie, bez przełączania"}
          >
            {chapterViewAll ? "📄 Widok: pojedynczo" : "📚 Widok: wszystkie"}
          </button>
        )}
        {documentType && EDITOR_TYPES.has(documentType) && (
          <NavLink to={`/${documentType}/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>✏️ Edytuj</NavLink>
        )}
        <NavLink to={`/chunks/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>Przegląd chunków</NavLink>
        <NavLink to={`/llm-costs?document_id=${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>💰 Koszty LLM</NavLink>
        {listNeighbors?.previous_id && <NavLink to={`/read/${listNeighbors.previous_id}${listReaderSearch}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>← Poprzedni</NavLink>}
        {listNeighbors?.next_id && <NavLink to={`/read/${listNeighbors.next_id}${listReaderSearch}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>Następny →</NavLink>}
        <NavLink to={`/list${listContext ? `?${listContext}` : ""}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>← Lista dokumentów</NavLink>
        <div style={{ marginLeft: "auto" }}><ReaderIdentityBadge identity={identity} /></div>
      </div>

      {(docPublishedOn || docIngestedAt || (docUrl && isOpenableSourceUrl(docUrl))) && (
        <div style={{ fontSize: "0.82em", color: "#64748b", marginBottom: 10, display: "flex", gap: 14, flexWrap: "wrap" }}>
          {docPublishedOn && <span>📅 Opublikowano: {new Date(docPublishedOn).toLocaleDateString("pl-PL")}</span>}
          {docIngestedAt && <span>Dodano do Lenie: {new Date(docIngestedAt).toLocaleDateString("pl-PL")}</span>}
          {docUrl && isOpenableSourceUrl(docUrl) && (
            <a href={toOpenableSourceUrl(docUrl)} target="_blank" rel="noreferrer" style={{ color: "#0369a1", wordBreak: "break-all" }}>
              🔗 Oryginał ↗
            </a>
          )}
        </div>
      )}

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      {id && <ChapterGroupsPanel documentId={id} position={position} />}

      <div
        className={`${styles.scrim} ${tocOpen ? styles.scrimOpen : ""}`}
        onClick={() => setTocOpen(false)}
      />

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        {/* TOC sidebar + notes */}
        {hasReaderSidebar && <div
          id="reader-sidebar"
          className={`${styles.tocPanel} ${tocOpen ? styles.tocPanelOpen : ""} ${!readerSidebarVisible ? styles.tocPanelCollapsed : ""}`}
        >
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
                  <span onClick={() => goToChapter(ch.position)}
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
        </div>}

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
          {loading && !chapterViewAll && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
          {!loading && content && !chapterViewAll && (
            <article style={{ fontSize: "1.02em" }} onContextMenu={onTextContextMenu}>
              {renderMarkdown(
                content.text, chapterNotes, referencesByMarker, highlightTerms, timelineHighlight?.quote,
                imagesByPosition, handleAnchorClick, wikiLinksByTitle, entityDescriptions,
              )}
            </article>
          )}
          {!loading && content && !chapterViewAll && (content.references?.length ?? 0) > 0 && (
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
          {!loading && content && !chapterViewAll && (content.images?.filter(img => !img.inline).length ?? 0) > 0 && (
            <details open style={{
              marginTop: 24, padding: "10px 14px", background: "#f8fafc",
              border: "1px solid #e2e8f0", borderRadius: 8,
            }}>
              <summary style={{ cursor: "pointer", fontSize: "0.9em", fontWeight: 600 }}>
                🖼 Ilustracje ({content.images!.filter(img => !img.inline).length})
              </summary>
              <div style={{ marginTop: 8 }}>
                {content.images!.filter(img => !img.inline).map((img, i) => renderChapterImage(img, i))}
              </div>
            </details>
          )}
          {chapterViewAll && allChaptersLoading && (
            <p style={{ color: "#64748b" }}>Ładowanie wszystkich rozdziałów…</p>
          )}
          {chapterViewAll && !allChaptersLoading && (allChapters ?? []).map((ch, idx) => {
            const chNotes = content?.chapter_total === 1 ? notes : notes.filter(n => n.chapter_position === ch.position);
            const chRefs = new Map((ch.references ?? []).map(r => [r.marker, r]));
            const chImages = new Map(
              (ch.images ?? [])
                .filter((img): img is ChapterImage & { position: number } => img.position !== null)
                .map(img => [img.position, img]),
            );
            const chWikiLinks = new Map(Object.entries(ch.wiki_links ?? {}));
            const chNonInlineImages = ch.images?.filter(img => !img.inline) ?? [];
            return (
              <div key={ch.position} id={`chapter-${ch.position}`} style={{ marginBottom: 40 }}>
                <h2 style={{ borderBottom: "1px solid #e2e8f0", paddingBottom: 8 }}>
                  {ch.position}. {ch.title}
                </h2>
                <article style={{ fontSize: "1.02em" }} onContextMenu={onTextContextMenu}>
                  {renderMarkdown(
                    ch.text, chNotes, chRefs, highlightTerms, timelineHighlight?.quote,
                    chImages, handleAnchorClick, chWikiLinks, entityDescriptions,
                  )}
                </article>
                {chRefs.size > 0 && (
                  <details open style={{
                    marginTop: 24, padding: "10px 14px", background: "#f8fafc",
                    border: "1px solid #e2e8f0", borderRadius: 8,
                  }}>
                    <summary style={{ cursor: "pointer", fontSize: "0.9em", fontWeight: 600 }}>
                      📚 Przypisy ({chRefs.size})
                    </summary>
                    <ol style={{ fontSize: "0.82em", color: "#475569", lineHeight: 1.5, margin: "8px 0 0", paddingLeft: 28 }}>
                      {(ch.references ?? []).map((r, i) => (
                        <li key={i} id={`fn-${r.marker}`} value={Number(r.marker) || undefined} style={{ margin: "4px 0" }}>
                          {renderRefText(r)}
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
                {chNonInlineImages.length > 0 && (
                  <details open style={{
                    marginTop: 24, padding: "10px 14px", background: "#f8fafc",
                    border: "1px solid #e2e8f0", borderRadius: 8,
                  }}>
                    <summary style={{ cursor: "pointer", fontSize: "0.9em", fontWeight: 600 }}>
                      🖼 Ilustracje ({chNonInlineImages.length})
                    </summary>
                    <div style={{ marginTop: 8 }}>
                      {chNonInlineImages.map((img, i) => renderChapterImage(img, i))}
                    </div>
                  </details>
                )}
                {idx < (allChapters?.length ?? 0) - 1 && (
                  <hr style={{ margin: "28px 0", border: "none", borderTop: "2px dashed #cbd5e1" }} />
                )}
              </div>
            );
          })}
          {navButtons}
        </div>

        {/* Map + entities + tags + synthesis — desktop only */}
        {isDesktop && (
          <>
          <div className={`${styles.rightPanel} ${(!hasObsidianPanel || !obsidianPanelVisible) ? styles.rightPanelExpanded : ""}`}>
            {!readerCompact && !chapterViewAll && <div style={{ fontSize: "0.78em", color: "#64748b", display: "flex", gap: 8, alignItems: "center" }}>
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
                    {source.review_status === "approved"
                      ? <span style={{ marginLeft: 6, fontSize: "0.72em", color: "#15803d" }}>✓ zatwierdzone</span>
                      : <button type="button" onClick={() => void approveInformationSource(source)} style={{ marginLeft: 6, fontSize: "0.72em" }}>Zatwierdź</button>}
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
            {relationshipGraph && <RelationshipGraph data={relationshipGraph} />}
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
                ⚠️ Wykrywanie osób, organizacji i miejsc nie powiodło się — serwis NER był niedostępny
                ({new Date(nerUnavailableAt).toLocaleString("pl-PL")}). Lista poniżej może być pusta lub niepełna,
                niekoniecznie dlatego, że w dokumencie nic nie ma. Spróbuj ponownej analizy w edytorze dokumentu.
              </div>
            )}

            {!nerUnavailableAt && !entitiesCheckedAt && (
              <div style={{
                background: "#f8fafc", border: "1px dashed #cbd5e1", borderRadius: 8,
                padding: 10, marginTop: 12, fontSize: "0.85em", color: "#64748b",
              }}>
                ℹ️ Ten dokument nie został jeszcze przeanalizowany pod kątem osób, organizacji i miejsc —
                lista poniżej jest pusta, bo nikt jej nie sprawdzał, nie dlatego że nic w nim nie ma.
                Uruchom wykrywanie encji w edytorze dokumentu.
              </div>
            )}

            {scoped && !shownPersons.length && !shownOrganizations.length && !shownPlaceItems.length
              && !shownCountries.length && !shownMarkers.length && (
              <div style={{ fontSize: "0.8em", color: "#94a3b8", marginTop: 8 }}>
                Brak osób, organizacji i miejsc w tym rozdziale.
              </div>
            )}

            <details open style={{
              background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
              padding: 10, marginTop: 12, fontSize: "0.9em",
            }}>
              <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 600 }}>
                Encje
              </summary>
              <div style={{ marginTop: 4 }}>
                <EntitiesPanel docId={id} countries={shownCountries} />
              </div>
            </details>

            <TimePeriodsPanel docId={id} currentChapter={position} />

            <TonePanel docId={id} currentChapter={position} />

            <TimelinePanel docId={id} currentChapter={position} onEventClick={handleTimelineEventClick} />

            <ContentGroupsPanel documentId={id} />

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

            {(docObsidianNotePaths.length > 0 || !!content?.chapter_obsidian_note_paths?.length) && (
              <details open style={{
                background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
                padding: 10, marginTop: 12,
              }}>
                <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 600 }}>
                  📝 Notatki Obsidian ({new Set([
                    ...docObsidianNotePaths, ...(content?.chapter_obsidian_note_paths ?? []),
                  ]).size})
                </summary>
                <div style={{ fontSize: "0.8em", marginTop: 8 }}>
                  {docObsidianNotePaths.length > 0 && (
                    <div>
                      Notatka dokumentu:{" "}
                      {docObsidianNotePaths.map((notePath, i) => (
                        <React.Fragment key={notePath}>
                          {i > 0 && ", "}
                          <a href={buildObsidianNoteUrl(notePath)} title={`Otwórz w Obsidianie: ${notePath}`}>
                            {notePath.split("/").pop()?.replace(/\.md$/i, "")}
                          </a>
                        </React.Fragment>
                      ))}
                    </div>
                  )}
                  {!!content?.chapter_obsidian_note_paths?.length && (
                    <div style={{ marginTop: docObsidianNotePaths.length > 0 ? 4 : 0 }}>
                      Notatka tego rozdziału:{" "}
                      {content.chapter_obsidian_note_paths.map((notePath, i) => (
                        <React.Fragment key={notePath}>
                          {i > 0 && ", "}
                          <a href={buildObsidianNoteUrl(notePath)} title={`Otwórz w Obsidianie: ${notePath}`}>
                            {notePath.split("/").pop()?.replace(/\.md$/i, "")}
                          </a>
                        </React.Fragment>
                      ))}
                    </div>
                  )}
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

            {/* Outside the rightPanelLoading branch on purpose: EntitiesPanel must
                not unmount/remount when chapter-scope loading toggles, or its
                mount-effect fetch → onEntitiesChanged → entitiesEditVersion bump →
                chapter-scope refetch → chapterScopeLoading toggle would remount it
                again, looping forever. */}
            {false && (
              <details open style={{
                background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
                padding: 10, marginTop: 12, fontSize: "0.9em",
              }}>
                <summary style={{ cursor: "pointer", fontSize: "0.85em", fontWeight: 600 }}>
                  ✏️ Edytuj encje
                </summary>
                <div style={{ marginTop: 8, fontSize: "0.85em", color: "#64748b" }}>
                  Obiekty infrastruktury są widoczne w tej samej liście.
                </div>
                <div style={{ marginTop: 4 }}>
                  <EntitiesPanel docId={id} onEntitiesChanged={handleEntitiesEdited} />
                </div>
              </details>
            )}
          </div>
          {hasObsidianPanel && obsidianPanelVisible && (
            <aside id="obsidian-panel" className={styles.obsidianPanel} aria-label="Zaimportowane notatki Obsidian">
              <div className={styles.obsidianPreviewHeader}>
                <strong>📝 Notatka Obsidian</strong>
                {importedObsidianNotes.length > 1 && (
                  <select
                    value={selectedObsidianNotePath ?? ""}
                    onChange={event => {
                      resetObsidianBrowse();
                      setSelectedObsidianNotePath(event.target.value);
                    }}
                    aria-label="Wybierz notatkę Obsidian"
                  >
                    {importedObsidianNotes.map(note => (
                      <option key={note.path} value={note.path}>{note.title}</option>
                    ))}
                  </select>
                )}
              </div>
              {obsidianBrowseNote && (
                <div className={styles.obsidianPreviewMeta}>
                  <button type="button" onClick={goBackObsidianBrowse} title="Wstecz" aria-label="Wstecz">
                    ← Wstecz
                  </button>
                  <button
                    type="button"
                    onClick={resetObsidianBrowse}
                    title="Powrót do notatek tego rozdziału"
                    aria-label="Powrót do notatek tego rozdziału"
                  >
                    🏠 Rozdział
                  </button>
                </div>
              )}
              {obsidianNotesLoading || obsidianBrowseLoading ? (
                <p className={styles.obsidianPreviewStatus}>Ładowanie notatki…</p>
              ) : displayedObsidianNote && (
                <>
                  <div className={styles.obsidianPreviewMeta}>
                    <span>{displayedObsidianNote.title}</span>
                    <NavLink to={`/read/${displayedObsidianNote.id}`} title="Otwórz jako artykuł czytnika">⤢</NavLink>
                    <a href={buildObsidianNoteUrl(displayedObsidianNote.path)} title="Otwórz w Obsidianie">↗</a>
                  </div>
                  <article className={styles.obsidianPreviewContent}>
                    {renderMarkdown(
                      displayedObsidianNote.text, [], undefined, undefined, undefined, undefined, undefined,
                      displayedObsidianNote.wiki_links
                        ? new Map(Object.entries(displayedObsidianNote.wiki_links))
                        : undefined,
                      undefined, openObsidianNoteInPanel,
                    )}
                  </article>
                </>
              )}
            </aside>
          )}
          </>
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
