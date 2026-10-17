import React from "react";

const normalize = (value: string) =>
  value.replace(/[*_`]+/g, "").replace(/\s+/g, " ").trim().toLocaleLowerCase("pl");

const asPlainText = (raw: string) => {
  if (!raw) return "";
  if (!/<[a-z][\s\S]*>/i.test(raw)) return raw;
  const document = new DOMParser().parseFromString(raw, "text/html");
  document.querySelectorAll("script, style, noscript").forEach(node => node.remove());
  const blocks = Array.from(document.body.querySelectorAll(
    "h1, h2, h3, h4, h5, h6, p, li, blockquote, figcaption",
  ))
    .map(node => node.textContent?.replace(/\s+/g, " ").trim() || "")
    .filter(Boolean);
  return blocks.length ? blocks.join("\n") : (document.body.textContent || "");
};

const usefulLines = (value: string) =>
  value.split(/\r?\n/).map(line => line.replace(/\s+/g, " ").trim()).filter(Boolean);

const MIN_MATCH_LENGTH = 24;

const findBoundary = (source: string[], candidates: string[], fromEnd = false) => {
  const ordered = fromEnd ? [...candidates].reverse() : candidates;
  for (const candidate of ordered) {
    const needle = normalize(candidate);
    if (needle.length < MIN_MATCH_LENGTH) continue;
    const index = source.findIndex(line => {
      const haystack = normalize(line);
      // Both sides must clear the length floor — otherwise a short nav/menu
      // line (e.g. a single word repeated in the page chrome) can trivially
      // satisfy needle.includes(haystack) just by containing that word.
      if (haystack.length < MIN_MATCH_LENGTH) return false;
      return haystack.includes(needle) || needle.includes(haystack);
    });
    if (index >= 0) return index;
  }
  return -1;
};

const ContextBlock = ({
  title, lines, muted = false, onAttach, attachLabel,
}: {
  title: string; lines: string[]; muted?: boolean;
  // Receives the index of the clicked line; the caller attaches the span from
  // that line to the article edge, so lines are never attached out of order.
  onAttach?: (index: number) => void; attachLabel?: (index: number) => string;
}) => (
  <section style={{
    padding: 9,
    background: muted ? "#f8fafc" : "#fff",
    color: muted ? "#64748b" : "#1e293b",
    borderBottom: "1px solid #e2e8f0",
  }}>
    <strong style={{ display: "block", marginBottom: 5, fontSize: "0.82em" }}>{title}</strong>
    {lines.length
      ? lines.map((line, index) => (
        <div key={index} style={{ display: "flex", gap: 6, alignItems: "flex-start", marginBottom: 6 }}>
          {onAttach && (
            <button type="button" className="button" style={{ flex: "none", padding: "0 6px" }}
              title={attachLabel?.(index)} onClick={() => onAttach(index)}>＋</button>
          )}
          <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{line}</div>
        </div>
      ))
      : <em style={{ color: "#94a3b8" }}>Brak wykrytego kontekstu.</em>}
  </section>
);

const ArticleSourceComparison = ({ formik }: { formik: any }) => {
  const raw = asPlainText(formik.values.text_raw || "");
  const sourceLines = usefulLines(raw);
  const articleLines = usefulLines(formik.values.text_md || formik.values.text || "");
  const start = findBoundary(sourceLines, articleLines.slice(0, 12));
  const end = findBoundary(sourceLines, articleLines.slice(-12), true);
  const boundariesFound = start >= 0 && end >= start;

  const before = boundariesFound
    ? sourceLines.slice(Math.max(0, start - 12), start)
    : sourceLines.slice(0, 12);
  const sourceArticle = boundariesFound
    ? sourceLines.slice(start, end + 1)
    : articleLines;
  const after = boundariesFound
    ? sourceLines.slice(end + 1, end + 13)
    : sourceLines.slice(-12);

  const currentText: string = formik.values.text_md || formik.values.text || "";
  // Source lines are plain text paragraphs; markdown paragraphs are blank-line separated.
  const attachBefore = (index: number) => formik.setFieldValue(
    "text_md", [...before.slice(index), currentText].join("\n\n"));
  const attachAfter = (index: number) => formik.setFieldValue(
    "text_md", [currentText, ...after.slice(0, index + 1)].join("\n\n"));
  const canAttach = raw !== "";

  return (
    <aside style={{ position: "sticky", top: 8, alignSelf: "start", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
        <strong>Kontrola kompletności względem źródła</strong>
        {formik.values.url && (
          <a href={formik.values.url} target="_blank" rel="noreferrer" style={{ marginLeft: "auto" }}>
            Otwórz oryginał ↗
          </a>
        )}
      </div>
      <div style={{
        border: "1px solid #cbd5e1", borderRadius: 6, overflow: "auto",
        maxHeight: "78vh", fontSize: "0.84em", lineHeight: 1.45,
      }}>
        {!raw && (
          <div style={{ padding: 10, background: "#fef3c7", color: "#92400e" }}>
            Brak przechwyconego materiału źródłowego. Porównaj dokument przez link do oryginału.
          </div>
        )}
        {raw && !boundariesFound && (
          <div style={{ padding: 8, background: "#fef3c7", color: "#92400e" }}>
            Nie udało się jednoznacznie odnaleźć granic artykułu w materiale źródłowym.
            Pokazano początek i koniec źródła oraz aktualny artykuł.
          </div>
        )}
        <ContextBlock title="Przed artykułem — materiał pominięty" lines={before} muted
          onAttach={canAttach ? attachBefore : undefined}
          attachLabel={index => `Dołącz na początku artykułu ${before.length - index} akapit(y) od tej linii (zapisz, aby zachować)`} />
        <ContextBlock title="Artykuł w materiale źródłowym" lines={sourceArticle} />
        <ContextBlock title="Po artykule — materiał pominięty" lines={after} muted
          onAttach={canAttach ? attachAfter : undefined}
          attachLabel={index => `Dołącz na końcu artykułu ${index + 1} akapit(y) do tej linii (zapisz, aby zachować)`} />
      </div>
    </aside>
  );
};

export default ArticleSourceComparison;
