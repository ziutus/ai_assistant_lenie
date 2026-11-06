import type { UserNote } from "../components/ReaderNotes/readerNotes";

/** A passage found on request by `POST /document/:id/chapter/:pos/detect_tone_spans` (library/tone_spans.py). */
export interface ToneSpan {
  id: number;
  chapter_position: number | null;
  /** `outlier` = its tone differs from the rest of the chapter; `key` = it carries the substance, whatever its tone. */
  role: "outlier" | "key";
  label: string;
  /** Verbatim text of the document, so the reader can find it. */
  quote: string;
  note: string | null;
  importance: number | null;
  status: "proposed" | "confirmed" | "rejected";
  model: string | null;
}

export const STANCE_OUTLIER = "tone_outlier";
export const STANCE_KEY = "tone_key";

interface ToneSpanStyle {
  icon: string;
  background: string;
  underline: string;
  /** Whole-paragraph tint, used when only a typography-normalised match of the quote is possible. */
  tint: string;
  tintBorder: string;
}

const STYLES: Record<string, ToneSpanStyle> = {
  [STANCE_OUTLIER]: { icon: "⚠️", background: "#fecaca", underline: "2px solid #ef4444", tint: "#fef2f2", tintBorder: "#ef4444" },
  [STANCE_KEY]: { icon: "⭐", background: "#bbf7d0", underline: "2px solid #16a34a", tint: "#f0fdf4", tintBorder: "#22c55e" },
};

/** Style of a highlight made from a tone passage; null for an ordinary reader note. */
export const toneSpanStyle = (stance: string | null | undefined): ToneSpanStyle | null =>
  (stance && STYLES[stance]) || null;

export const ROLE_LABEL: Record<ToneSpan["role"], string> = { outlier: "odstaje tonem", key: "kluczowy" };

/**
 * A passage as a synthetic reader note, so the reader's existing quote highlighting draws it. The id is negative
 * (never a stored note's id) and the stance carries the role.
 */
export const toneSpanToNote = (span: ToneSpan, documentId: number): UserNote => ({
  id: -span.id,
  user_id: 0,
  document_id: documentId,
  chapter_position: span.chapter_position,
  anchor_quote: span.quote,
  anchor_prefix: null,
  anchor_suffix: null,
  run_id: null,
  chunk_id: null,
  note_text: [`${span.label}${span.status === "confirmed" ? " ✓" : ""}`, span.note].filter(Boolean).join(" — "),
  tags: [],
  stance: span.role === "key" ? STANCE_KEY : STANCE_OUTLIER,
  created_at: null,
  updated_at: null,
});

/**
 * Passages to show for the chapter on screen. A document without `##` chapters stores them with a NULL position, and
 * a compact reader (a short article with several headings shown as one chapter) shows every chapter's passages.
 * Rejected passages are never highlighted.
 */
export const visibleToneSpans = (spans: ToneSpan[], position: number, compact: boolean): ToneSpan[] =>
  spans.filter((span) =>
    span.status !== "rejected"
    && (compact || span.chapter_position === null || span.chapter_position === position));

interface SplittableMatch {
  idx: number;
  len: number;
  note?: { stance: string | null } | null;
}

/**
 * The reader cannot nest highlights, but the most valuable sentence of a text may sit INSIDE a malicious remark. An
 * outlier match that contains a key match is therefore cut around it: the outlier's text before and after the key
 * sentence stays marked, the key sentence gets its own mark.
 */
export function splitOutliersAroundKeys<M extends SplittableMatch>(matches: M[]): M[] {
  const keys = matches.filter((match) => match.note?.stance === STANCE_KEY);
  if (keys.length === 0) return matches;
  const result: M[] = [];
  for (const match of matches) {
    if (match.note?.stance !== STANCE_OUTLIER) {
      result.push(match);
      continue;
    }
    const end = match.idx + match.len;
    const inside = keys
      .filter((key) => key.idx >= match.idx && key.idx + key.len <= end)
      .sort((a, b) => a.idx - b.idx);
    if (inside.length === 0) {
      result.push(match);
      continue;
    }
    let cursor = match.idx;
    for (const key of inside) {
      if (key.idx < cursor) continue; // overlapping keys: the first one wins
      if (key.idx > cursor) result.push({ ...match, idx: cursor, len: key.idx - cursor });
      cursor = key.idx + key.len;
    }
    if (cursor < end) result.push({ ...match, idx: cursor, len: end - cursor });
  }
  return result.sort((a, b) => a.idx - b.idx);
}
