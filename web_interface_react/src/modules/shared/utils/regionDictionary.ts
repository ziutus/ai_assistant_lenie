// Region dictionary (GET /document/:id/transcript_corrections): the stored correction rules of the document's
// countries (kraj-* tags) and what they really changed in the transcript. The corrected text no longer holds the
// original wording, so the backend keeps an audit row per (rule, wording, chapter) and the reader shows it.

export type RegionApplication = {
  rule_id: number | null;
  scope: string | null;
  country_slug: string | null;
  original_text: string;
  replacement_text: string;
  chapter_position: number;
  occurrences: number;
  applied_at: string | null;
};

export type RegionDictionaryInfo = {
  author: string | null;
  applications: RegionApplication[];
  dictionaries: { country_slug: string; country_name: string | null; rules: number }[];
  pending_changes: number;
};

export type ChapterChange = { original: string; replacement: string; occurrences: number };

// What the dictionaries changed in ONE chapter, one line per (original -> replacement) pair, most frequent first.
export function changesInChapter(info: RegionDictionaryInfo | null | undefined, position: number): ChapterChange[] {
  const lines = new Map<string, ChapterChange>();
  (info?.applications ?? []).filter((application) => application.chapter_position === position).forEach((application) => {
    const key = `${application.original_text}\u0000${application.replacement_text}`;
    const line = lines.get(key) ?? { original: application.original_text, replacement: application.replacement_text, occurrences: 0 };
    line.occurrences += application.occurrences;
    lines.set(key, line);
  });
  return [...lines.values()].sort((a, b) => b.occurrences - a.occurrences || a.original.localeCompare(b.original));
}

export type DictionaryChange = { original: string; replacement: string; occurrences: number; chapters: number[] };
export type DictionarySummary = {
  country_slug: string; name: string; rules: number; total: number; changes: DictionaryChange[];
};

// What ONE country's dictionary changed in the whole document: one line per (original -> replacement) with the
// chapters it happened in, most frequent first. Countries known only from old audit rows (their rules were
// removed or the tag dropped) are listed too, so no recorded change is hidden.
export function summaryByCountry(info: RegionDictionaryInfo | null | undefined): DictionarySummary[] {
  if (!info) return [];
  const summaries = new Map<string, DictionarySummary>();
  info.dictionaries.forEach((dictionary) => summaries.set(dictionary.country_slug, {
    country_slug: dictionary.country_slug, name: dictionary.country_name ?? dictionary.country_slug,
    rules: dictionary.rules, total: 0, changes: [],
  }));
  const lines = new Map<string, DictionaryChange>();
  info.applications.forEach((application) => {
    const slug = application.country_slug;
    if (!slug) return;
    if (!summaries.has(slug)) {
      summaries.set(slug, { country_slug: slug, name: slug.replace(/^kraj-/, ""), rules: 0, total: 0, changes: [] });
    }
    const summary = summaries.get(slug)!;
    const key = `${slug}\u0000${application.original_text}\u0000${application.replacement_text}`;
    let line = lines.get(key);
    if (!line) {
      line = { original: application.original_text, replacement: application.replacement_text, occurrences: 0, chapters: [] };
      lines.set(key, line);
      summary.changes.push(line);
    }
    line.occurrences += application.occurrences;
    summary.total += application.occurrences;
    if (!line.chapters.includes(application.chapter_position)) line.chapters.push(application.chapter_position);
  });
  summaries.forEach((summary) => {
    summary.changes.forEach((line) => line.chapters.sort((a, b) => a - b));
    summary.changes.sort((a, b) => b.occurrences - a.occurrences || a.original.localeCompare(b.original));
  });
  return [...summaries.values()];
}

// "Jemen" for one country, "Jemen, Iran" for several; the name of a dictionary beats the bare slug of an old audit row.
export const regionLabel = (info: RegionDictionaryInfo): string => {
  const names = new Map<string, string>();
  info.dictionaries.forEach((dictionary) => names.set(dictionary.country_slug, dictionary.country_name ?? dictionary.country_slug));
  info.applications.forEach((application) => {
    if (application.country_slug && !names.has(application.country_slug)) {
      names.set(application.country_slug, application.country_slug.replace(/^kraj-/, ""));
    }
  });
  return [...names.values()].join(", ");
};

// Pending text changes returned by POST /transcript_corrections/apply.
export type PendingDictionaryChange = {
  rule_id: number;
  scope: "global" | "author" | "region";
  country_slug: string | null;
  pattern: string;
  replacement: string;
  occurrences: number;
  chapters: number[];
  wordings: ChapterChange[];
};

export const formatChapterNumbers = (chapters: number[]): string =>
  chapters.map((chapter) => chapter === 0 ? "wstęp" : String(chapter)).join(", ");
