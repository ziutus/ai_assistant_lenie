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

const findBoundary = (source: string[], candidates: string[], fromEnd = false) => {
  const ordered = fromEnd ? [...candidates].reverse() : candidates;
  for (const candidate of ordered) {
    const needle = normalize(candidate);
    if (needle.length < 24) continue;
    const index = source.findIndex(line => {
      const haystack = normalize(line);
      return haystack.includes(needle) || needle.includes(haystack);
    });
    if (index >= 0) return index;
  }
  return -1;
};

const ContextBlock = ({
  title, lines, muted = false,
}: { title: string; lines: string[]; muted?: boolean }) => (
  <section style={{
    padding: 9,
    background: muted ? "#f8fafc" : "#fff",
    color: muted ? "#64748b" : "#1e293b",
    borderBottom: "1px solid #e2e8f0",
  }}>
    <strong style={{ display: "block", marginBottom: 5, fontSize: "0.82em" }}>{title}</strong>
    {lines.length
      ? <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{lines.join("\n\n")}</div>
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
        <ContextBlock title="Przed artykułem — materiał pominięty" lines={before} muted />
        <ContextBlock title="Artykuł w materiale źródłowym" lines={sourceArticle} />
        <ContextBlock title="Po artykule — materiał pominięty" lines={after} muted />
      </div>
    </aside>
  );
};

export default ArticleSourceComparison;
