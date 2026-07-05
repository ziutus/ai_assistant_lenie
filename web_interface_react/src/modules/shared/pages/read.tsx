import React from "react";
import { useParams, useSearchParams, NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// ── Types ────────────────────────────────────────────────────────────────────

interface Chapter {
  position: number;
  level: number;
  title: string;
  char_start: number;
  char_end: number;
  length: number;
}

interface ChapterContent {
  position: number;
  title: string;
  text: string;
  chapter_total: number;
  prev: number | null;
  next: number | null;
}

// ── Minimal markdown rendering (headings, paragraphs, hr; images skipped) ────

const IMAGE_LINE = /^!\[[^\]]*\]\([^)]*\)$/;

function renderInline(text: string): React.ReactNode[] {
  // **bold** and *italic* only — enough for OCR-ed book prose
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
    return part;
  });
}

function renderMarkdown(text: string): React.ReactNode[] {
  const blocks = text.split(/\n\s*\n/);
  const out: React.ReactNode[] = [];
  blocks.forEach((block, i) => {
    const trimmed = block.trim();
    if (!trimmed || IMAGE_LINE.test(trimmed)) return;
    const heading = trimmed.match(/^(#{1,6})\s+(.*)$/s);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 6);
      const Tag = `h${level}` as keyof JSX.IntrinsicElements;
      out.push(<Tag key={i} style={{ marginTop: level === 2 ? 0 : 28 }}>{heading[2]}</Tag>);
      return;
    }
    if (trimmed === "---") {
      out.push(<hr key={i} style={{ margin: "20px 0", border: "none", borderTop: "1px solid #e2e8f0" }} />);
      return;
    }
    // footnote / caption lines (superscript digits or "Wykres N.") — smaller font
    const isNote = /^([¹²³⁴⁵⁶⁷⁸⁹⁰]+|\d{1,3} )\S*\s*(http|www|[A-ZŻŹĆĄŚĘŁÓŃ])/.test(trimmed) && trimmed.length < 400;
    out.push(
      <p key={i} style={isNote
        ? { fontSize: "0.8em", color: "#64748b", margin: "6px 0" }
        : { lineHeight: 1.65, margin: "14px 0", textAlign: "justify" }}>
        {renderInline(trimmed.replace(/\n/g, " "))}
      </p>
    );
  });
  return out;
}

// ── Page ─────────────────────────────────────────────────────────────────────

const Read: React.FC = () => {
  const { id } = useParams();
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();

  const [chapters, setChapters] = React.useState<Chapter[]>([]);
  const [content, setContent] = React.useState<ChapterContent | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const contentRef = React.useRef<HTMLDivElement>(null);

  const position = Number(searchParams.get("chapter") ?? 1);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);

  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/chapters`, { headers });
        const data = await r.json();
        if (data.status !== "success") throw new Error(data.message ?? "Błąd pobierania rozdziałów");
        setChapters(data.chapters ?? []);
      } catch (e) {
        setError(String(e));
      }
    })();
  }, [apiUrl, id, headers]);

  React.useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const r = await fetch(`${apiUrl}/document/${id}/chapter/${position}`, { headers });
        const data = await r.json();
        if (data.status !== "success") throw new Error(data.message ?? "Błąd pobierania rozdziału");
        setContent(data);
        contentRef.current?.scrollTo({ top: 0 });
        window.scrollTo({ top: 0 });
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [apiUrl, id, position, headers]);

  const goTo = (pos: number | null) => {
    if (pos) setSearchParams({ chapter: String(pos) });
  };

  const navButtons = content && (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, margin: "18px 0" }}>
      <button onClick={() => goTo(content.prev)} disabled={!content.prev}
        style={{ padding: "6px 14px", cursor: content.prev ? "pointer" : "default" }}>
        ← Poprzedni
      </button>
      <span style={{ fontSize: "0.85em", color: "#64748b", alignSelf: "center" }}>
        {content.position} / {content.chapter_total}
      </span>
      <button onClick={() => goTo(content.next)} disabled={!content.next}
        style={{ padding: "6px 14px", cursor: content.next ? "pointer" : "default" }}>
        Następny →
      </button>
    </div>
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Czytelnik — dokument #{id}</h2>
        <NavLink to={`/chunks/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>Przegląd chunków</NavLink>
        <NavLink to="/list" style={{ fontSize: "0.85em", color: "#0369a1" }}>← Lista dokumentów</NavLink>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        {/* TOC sidebar */}
        <nav style={{
          flex: "0 0 280px", position: "sticky", top: 12, maxHeight: "85vh", overflowY: "auto",
          background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 0",
        }}>
          <strong style={{ fontSize: "0.85em", padding: "0 14px" }}>Spis treści ({chapters.length})</strong>
          {chapters.map(ch => (
            <div key={ch.position}
              onClick={() => goTo(ch.position)}
              style={{
                padding: "5px 14px", fontSize: "0.83em", cursor: "pointer", lineHeight: 1.3,
                background: ch.position === position ? "#e0f2fe" : undefined,
                fontWeight: ch.position === position ? 600 : undefined,
              }}>
              {ch.position}. {ch.title}
            </div>
          ))}
        </nav>

        {/* Chapter content */}
        <div ref={contentRef} style={{ flex: 1, maxWidth: 760 }}>
          {navButtons}
          {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
          {!loading && content && (
            <article style={{ fontSize: "1.02em" }}>{renderMarkdown(content.text)}</article>
          )}
          {navButtons}
        </div>
      </div>
    </div>
  );
};

export default Read;
