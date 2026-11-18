// Channel glossary (GET /ner_channel_glossary/applications?document_id=) as the reading views use it: the
// stored transcript keeps the author's wording ("Rzymianie"), the glossary says what the author means ("Żydzi").
// Both /ner/:id and /read/:id show the glossary name in the text, in its own colour, with a tooltip that gives
// the original wording and where the rule comes from.

export type GlossaryInfo = {
  author: string | null;
  entries: { id: number; canonical_name: string; aliases: string[]; fuzzy: boolean }[];
  applications: { original_text: string; replacement_text: string; occurrences: number }[];
};

export interface GlossarySwap {
  original: string;
  canonical: string;
}

export const GLOSSARY_COLOR = "#bae6fd";
export const GLOSSARY_UNDERLINE = "2px solid #0284c7";

// Every wording the glossary rewrites: the entries' exact aliases plus what the last entity refresh actually
// replaced (this also covers the sound-alike repairs of fuzzy entries). One pair per case-folded wording.
export function glossarySwaps(info: GlossaryInfo | null | undefined): GlossarySwap[] {
  if (!info?.author) return [];
  const swaps = new Map<string, GlossarySwap>();
  const add = (original: string, canonical: string) => {
    const wording = original?.trim();
    if (!wording || !canonical || wording === canonical || wording.length < 2) return;
    if (!swaps.has(wording.toLowerCase())) swaps.set(wording.toLowerCase(), { original: wording, canonical });
  };
  info.entries.forEach((entry) => entry.aliases.forEach((alias) => add(alias, entry.canonical_name)));
  info.applications.forEach((application) => add(application.original_text, application.replacement_text));
  return [...swaps.values()];
}

// "kanału" for a video channel, "autora" for everything else (the glossary is keyed by the document's byline).
export const glossaryScope = (documentType: string | null | undefined) =>
  documentType === "youtube" || documentType === "movie" ? "kanału" : "autora/źródła";

export function glossaryHint(info: GlossaryInfo, swap: GlossarySwap, documentType?: string | null): string {
  return `Ze słownika ${glossaryScope(documentType)} „${info.author}”: w tekście stoi „${swap.original}”, `
    + `czytane jako „${swap.canonical}”. Transkrypcja się nie zmienia.`;
}
