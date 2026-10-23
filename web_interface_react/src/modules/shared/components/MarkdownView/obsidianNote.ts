// Cleans a note copied from an Obsidian "application" template so that only the
// free-form body is left: the fixed facts (type, licence, pricing model, pricing
// page, homepage) live in dedicated fields of the tool, so repeating them in the
// note body would show them twice.

const FIXED_FIELD_LABELS = [
  "purpose", "type of application", "licence", "license", "homepage",
  "pricing type", "pricing page", "pricing", "cel", "typ aplikacji", "licencja", "cennik",
];

// "**Licence**: x", "**Licence:** x", "Licence: x" (only when bold — plain "Licence:" could be prose).
const FIXED_FIELD_RE = /^\s*\*\*\s*([^*:]+?)\s*:?\s*\*\*\s*:?\s*(.*)$/;

export type CleanedNote = { markdown: string; removed: string[] };

export function cleanObsidianNote(raw: string, toolName?: string): CleanedNote {
  const removed: string[] = [];
  let text = raw.replace(/\r\n?/g, "\n");

  const frontMatter = text.match(/^---\n[\s\S]*?\n---[ \t]*(\n|$)/);
  if (frontMatter) {
    text = text.slice(frontMatter[0].length);
    removed.push("front matter (tagi)");
  }

  // Everything from the template's "# Metadata" footer down is Templater output.
  const metadata = text.search(/^#{1,6}\s*Metadata\s*$/im);
  if (metadata >= 0) {
    text = text.slice(0, metadata);
    removed.push("sekcja Metadata");
  }
  if (/<%[\s\S]*?%>/.test(text)) {
    text = text.replace(/^.*<%[\s\S]*?%>.*\n?/gm, "");
    removed.push("znaczniki Templatera");
  }

  const lines = text.split("\n");
  const kept: string[] = [];
  let inFence = false;
  const stripped = new Set<string>();
  for (const line of lines) {
    if (/^\s*(```|~~~)/.test(line)) inFence = !inFence;
    if (!inFence) {
      const field = line.match(FIXED_FIELD_RE);
      if (field && FIXED_FIELD_LABELS.includes(field[1].trim().toLowerCase())) {
        stripped.add(field[1].trim());
        continue;
      }
    }
    kept.push(line);
  }
  if (stripped.size) removed.push(`pola stałe (${Array.from(stripped).join(", ")})`);

  // The template opens with "## <Tool name>"; the page already shows the name.
  if (toolName) {
    const first = kept.findIndex(line => line.trim() !== "");
    const name = toolName.trim().toLowerCase();
    if (first >= 0) {
      const heading = kept[first].match(/^#{1,6}\s+(.*?)\s*$/);
      if (heading && heading[1].trim().toLowerCase() === name) {
        kept.splice(first, 1);
        removed.push("nagłówek z nazwą narzędzia");
      }
    }
  }

  // The template's empty section headings ("# Source of note" with nothing under it) are noise.
  const withoutEmptyHeadings = dropEmptyHeadings(kept);
  const markdown = withoutEmptyHeadings.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  return { markdown, removed };
}

function dropEmptyHeadings(lines: string[]): string[] {
  const out: string[] = [];
  let inFence = false;
  lines.forEach((line, index) => {
    if (/^\s*(```|~~~)/.test(line)) inFence = !inFence;
    const heading = !inFence && line.match(/^(#{1,6})\s+\S/);
    if (!heading) { out.push(line); return; }
    const next = lines.slice(index + 1).find(candidate => candidate.trim() !== "");
    const nextHeading = next?.match(/^(#{1,6})\s+\S/);
    // Empty when the section has no body before the next heading of the same or a higher level, or the end.
    if (next === undefined || (nextHeading && nextHeading[1].length <= heading[1].length)) return;
    out.push(line);
  });
  return out;
}
