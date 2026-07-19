import React from "react";
import { buildObsidianNoteUrl } from "./modules/shared/utils/obsidian";

interface ListItemSearchSimilarProps {
  query: string;
  item: {
    similarity?: number | null;
    semantic_similarity?: number;
    text_score?: number;
    search_match?: "text" | "semantic" | "hybrid" | "filters_only";
    id: number | null;
    text?: string;
    title?: string | null;
    document_type?: string | null;
    website_id: number;
    url: string;
    published_on?: string | null;
    created_at?: string | null;
    chunk_id?: number | null;
    obsidian_note_paths?: string[];
  };
}

const formatDocDate = (value?: string | null) =>
  value ? new Date(value).toLocaleDateString("pl-PL") : null;

const meaningfulTerms = (query: string) =>
  Array.from(new Set(query.trim().split(/\s+/).filter(term => term.length >= 3)))
    .sort((a, b) => b.length - a.length);

const makeSnippet = (text: string | undefined, query: string, maxLength = 460) => {
  const compact = (text || "").replace(/\s+/g, " ").trim();
  if (compact.length <= maxLength) return compact;

  const lower = compact.toLocaleLowerCase("pl");
  const positions = meaningfulTerms(query)
    .map(term => lower.indexOf(term.toLocaleLowerCase("pl")))
    .filter(position => position >= 0);
  const matchAt = positions.length ? Math.min(...positions) : 0;
  let start = Math.max(0, matchAt - Math.floor(maxLength * 0.28));
  let end = Math.min(compact.length, start + maxLength);
  if (end === compact.length) start = Math.max(0, end - maxLength);
  if (start > 0) start = compact.indexOf(" ", start) + 1;
  if (end < compact.length) end = compact.lastIndexOf(" ", end);
  return `${start > 0 ? "…" : ""}${compact.slice(start, end)}${end < compact.length ? "…" : ""}`;
};

const Highlight = ({ text, query }: { text: string; query: string }) => {
  const terms = meaningfulTerms(query);
  if (!terms.length) return <>{text}</>;
  const escaped = terms.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "giu");
  return <>{text.split(regex).map((part, index) =>
    terms.some(term => term.toLocaleLowerCase("pl") === part.toLocaleLowerCase("pl")) ? (
      <mark key={index} style={{ background: "#fef08a", color: "inherit", padding: "0 1px", borderRadius: 2 }}>{part}</mark>
    ) : <React.Fragment key={index}>{part}</React.Fragment>
  )}</>;
};

const MATCH_LABELS = {
  text: "dopasowanie tekstowe",
  semantic: "dopasowanie semantyczne",
  hybrid: "dopasowanie hybrydowe",
  filters_only: "dopasowanie filtrów",
};

const ListItemSearchSimilar = ({ item, query }: ListItemSearchSimilarProps) => {
  const notes = item.obsidian_note_paths ?? [];
  const match = item.search_match ?? "semantic";
  const score = Math.round((item.similarity ?? 0) * 100);
  const snippet = makeSnippet(item.text, query);

  return (
    <article style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "16px 18px", background: "#fff", boxShadow: "0 1px 2px rgba(15,23,42,.04)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
        <div style={{ minWidth: 0 }}>
          <a href={`/read/${item.website_id}`} style={{ color: "#0f4c81", fontSize: "1.05rem", fontWeight: 700, lineHeight: 1.35, textDecoration: "none" }}>
            <Highlight text={item.title || `Dokument #${item.website_id}`} query={query} />
          </a>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 7, color: "#64748b", fontSize: ".76rem" }}>
            <span style={{ background: match === "text" ? "#ecfccb" : match === "hybrid" ? "#e0f2fe" : "#f1f5f9", color: "#334155", borderRadius: 999, padding: "2px 8px" }}>
              {MATCH_LABELS[match]}
            </span>
            {item.document_type && <span>{item.document_type}</span>}
            {formatDocDate(item.published_on) && <span title="Data publikacji">📅 {formatDocDate(item.published_on)}</span>}
            {!item.published_on && formatDocDate(item.created_at) && (
              <span title="Data dodania do Lenie (brak daty publikacji)">📅 dodano {formatDocDate(item.created_at)}</span>
            )}
            <span>ID {item.website_id}</span>
            {item.chunk_id != null && <span>chunk #{item.chunk_id}</span>}
          </div>
        </div>
        <div title={`Wynik dopasowania: ${item.similarity}`} style={{ flexShrink: 0, borderRadius: 999, background: score >= 70 ? "#dcfce7" : "#f1f5f9", color: score >= 70 ? "#166534" : "#475569", padding: "5px 9px", fontWeight: 700, fontSize: ".78rem" }}>
          {score}%
        </div>
      </div>

      {snippet && <p style={{ margin: "13px 0", color: "#334155", lineHeight: 1.58, fontSize: ".91rem" }}><Highlight text={snippet} query={query} /></p>}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "center", fontSize: ".82rem" }}>
        <a href={`/read/${item.website_id}`} style={{ fontWeight: 600 }}>📖 Czytaj</a>
        {item.chunk_id != null && <a href={`/chunks/${item.website_id}`}>🧩 Otwórz chunki</a>}
        <a href={item.url} target="_blank" rel="noopener noreferrer">↗ Źródło</a>
        {notes.map(notePath => (
          <a key={notePath} href={buildObsidianNoteUrl(notePath)} title={`Otwórz w Obsidianie: ${notePath}`}>
            📝 {notePath.split("/").pop()?.replace(/\.md$/i, "")}
          </a>
        ))}
      </div>
    </article>
  );
};

export default ListItemSearchSimilar;
