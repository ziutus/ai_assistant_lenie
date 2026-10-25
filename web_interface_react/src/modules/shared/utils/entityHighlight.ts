// Splits a sentence into plain and entity-mention segments for the /ner/:id review page.
// Matching mirrors backend entity_service.filter_entities_to_text(): case-insensitive whole
// tokens with Unicode boundaries, longest surface form first, and a capitalised surface form
// only matches a capitalised mention ("Unia" does not match "unia").

export type HighlightKind = "persName" | "place" | "orgName" | "country" | "event" | "product";

export interface HighlightEntry {
  variants: string[];
  kind: HighlightKind;
  label: string;
  // Extra tooltip line, e.g. the member countries of a group of states.
  hint?: string;
}

export interface HighlightSegment {
  text: string;
  kind?: HighlightKind;
  label?: string;
  hint?: string;
}

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function splitByEntities(text: string, entries: HighlightEntry[]): HighlightSegment[] {
  const needles = new Map<string, { needle: string; entry: HighlightEntry }>();
  for (const entry of entries) {
    for (const raw of entry.variants) {
      const needle = raw.trim();
      const key = needle.toLowerCase();
      if (needle && !needles.has(key)) needles.set(key, { needle, entry });
    }
  }
  if (!needles.size) return [{ text }];

  const ordered = [...needles.values()].sort((a, b) => b.needle.length - a.needle.length);
  const pattern = new RegExp(
    "(?<![\\p{L}\\p{N}_])(?:" + ordered.map(({ needle }) => escapeRegExp(needle)).join("|") + ")(?![\\p{L}\\p{N}_])",
    "giu",
  );

  const segments: HighlightSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const found = needles.get(match[0].toLowerCase()) ?? ordered.find(({ needle }) => needle.toLowerCase() === match[0].toLowerCase());
    if (!found) continue;
    const needleIsCapitalised = found.needle[0] !== found.needle[0].toLowerCase();
    const mentionIsCapitalised = match[0][0] !== match[0][0].toLowerCase();
    if (needleIsCapitalised && !mentionIsCapitalised) continue;
    const start = match.index ?? 0;
    if (start > last) segments.push({ text: text.slice(last, start) });
    segments.push({ text: match[0], kind: found.entry.kind, label: found.entry.label, hint: found.entry.hint });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last) });
  return segments.length ? segments : [{ text }];
}
