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
