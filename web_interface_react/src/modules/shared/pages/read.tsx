import React from "react";
import { useParams, useSearchParams, NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import {
  NotePopover, NoteRow, PendingNote, STANCE_ICON, UserNote, UserPicker,
  normalizeWs, pendingNoteFromSelection, useReaderIdentity, useUserNotes,
} from "../components/ReaderNotes/readerNotes";
import styles from "./read.module.css";

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

/** Render a paragraph's text with <mark> around anchored note quotes.
 *  Exact match → inline highlight; whitespace-normalized match → whole
 *  paragraph tinted (quote spans line breaks or renderer differences). */
function renderParagraphWithNotes(
  text: string,
  notes: UserNote[],
): { nodes: React.ReactNode[]; paragraphTint: UserNote | null } {
  const matches = notes
    .map(n => ({ note: n, idx: text.indexOf(n.anchor_quote) }))
    .filter(m => m.idx >= 0)
    .sort((a, b) => a.idx - b.idx);

  if (matches.length === 0) {
    const tint = notes.find(n => normalizeWs(text).includes(normalizeWs(n.anchor_quote))) ?? null;
    return { nodes: renderInline(text), paragraphTint: tint };
  }

  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  matches.forEach((m, i) => {
    if (m.idx < cursor) return; // overlapping quote — skip
    if (m.idx > cursor) nodes.push(...renderInline(text.slice(cursor, m.idx)));
    const quoted = text.slice(m.idx, m.idx + m.note.anchor_quote.length);
    nodes.push(
      <mark
        key={`note-${m.note.id}-${i}`}
        title={`${STANCE_ICON[m.note.stance ?? ""] ?? "📝"} ${m.note.note_text}`}
        style={{ background: "#fef08a", padding: "0 1px", cursor: "help" }}
      >
        {renderInline(quoted)}
      </mark>
    );
    cursor = m.idx + m.note.anchor_quote.length;
  });
  if (cursor < text.length) nodes.push(...renderInline(text.slice(cursor)));
  return { nodes, paragraphTint: null };
}

function renderMarkdown(text: string, notes: UserNote[]): React.ReactNode[] {
  const blocks = text.split(/\n\s*\n/);
  const out: React.ReactNode[] = [];
  blocks.forEach((block, i) => {
    const trimmed = block.trim();
    if (!trimmed || IMAGE_LINE.test(trimmed)) return;
    const heading = trimmed.match(/^(#{1,6})\s+(.*)$/s);
    if (heading) {
      const level = Math.min(heading[1].length + 1, 6);
      const Tag = `h${level}` as keyof JSX.IntrinsicElements;
      // headings can carry note anchors too (e.g. a quote of the chapter title)
      const { nodes } = renderParagraphWithNotes(heading[2].replace(/\n/g, " "), notes);
      out.push(<Tag key={i} style={{ marginTop: level === 2 ? 0 : 28 }}>{nodes}</Tag>);
      return;
    }
    if (trimmed === "---") {
      out.push(<hr key={i} style={{ margin: "20px 0", border: "none", borderTop: "1px solid #e2e8f0" }} />);
      return;
    }
    // footnote / caption lines (superscript digits or "Wykres N.") — smaller font
    const isNote = /^([¹²³⁴⁵⁶⁷⁸⁹⁰]+|\d{1,3} )\S*\s*(http|www|[A-ZŻŹĆĄŚĘŁÓŃ])/.test(trimmed) && trimmed.length < 400;
    const paraText = trimmed.replace(/\n/g, " ");
    const { nodes, paragraphTint } = renderParagraphWithNotes(paraText, notes);
    out.push(
      <p key={i} style={isNote
        ? { fontSize: "0.8em", color: "#64748b", margin: "6px 0" }
        : {
            lineHeight: 1.65, margin: "14px 0", textAlign: "justify",
            ...(paragraphTint ? { background: "#fefce8", borderLeft: "3px solid #eab308", paddingLeft: 8 } : {}),
          }}
        title={paragraphTint ? `📝 ${paragraphTint.note_text}` : undefined}>
        {nodes}
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
  const [tocOpen, setTocOpen] = React.useState(false);
  const contentRef = React.useRef<HTMLDivElement>(null);

  // ── Reading progress ──
  const [readChapters, setReadChapters] = React.useState<number[]>([]);
  const [progressLoaded, setProgressLoaded] = React.useState(false);
  const initialRedirectDone = React.useRef(false);

  // ── User identity + notes (shared with /chunks) ──
  const identity = useReaderIdentity(apiUrl, apiKey, () => {
    setProgressLoaded(false);
    initialRedirectDone.current = false;
  });
  const { userId, headers, jsonHeaders } = identity;
  const { notes, createNote, saveNoteText, deleteNote } = useUserNotes(apiUrl, id, identity);
  const [pendingNote, setPendingNote] = React.useState<PendingNote | null>(null);

  const position = Number(searchParams.get("chapter") ?? 1);

  // ── Data loading ──

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, apiKey]);

  // progress: fetch once per (user, doc); redirect to last position when URL has no ?chapter
  React.useEffect(() => {
    if (!userId) { setProgressLoaded(true); setReadChapters([]); return; }
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/reading_progress`, { headers });
        const data = await r.json();
        if (data.status === "success") {
          setReadChapters(data.read_chapters ?? []);
          if (!initialRedirectDone.current && !searchParams.get("chapter") && data.current_chapter) {
            setSearchParams({ chapter: String(data.current_chapter) }, { replace: true });
          }
        }
      } catch { /* progress is best-effort */ }
      initialRedirectDone.current = true;
      setProgressLoaded(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, userId]);

  // chapter content — waits for the progress redirect so we don't flash chapter 1
  React.useEffect(() => {
    if (!progressLoaded) return;
    (async () => {
      setLoading(true);
      setError(null);
      setPendingNote(null);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, position, progressLoaded, apiKey]);

  // persist current chapter as reading position
  React.useEffect(() => {
    if (!userId || !content || !progressLoaded) return;
    fetch(`${apiUrl}/document/${id}/reading_progress`, {
      method: "PUT", headers: jsonHeaders,
      body: JSON.stringify({ current_chapter: content.position, current_chapter_title: content.title }),
    }).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content?.position, userId]);

  // ── Actions ──

  const goTo = (pos: number | null) => {
    if (pos) setSearchParams({ chapter: String(pos) });
    setTocOpen(false);
  };

  const toggleRead = (pos: number, read: boolean) => {
    if (!userId) return;
    setReadChapters(prev => read ? [...prev, pos].sort((a, b) => a - b) : prev.filter(p => p !== pos));
    fetch(`${apiUrl}/document/${id}/reading_progress`, {
      method: "PUT", headers: jsonHeaders,
      body: JSON.stringify({
        current_chapter: position,
        [read ? "mark_read" : "unmark_read"]: [pos],
      }),
    }).catch(() => undefined);
  };

  const goNext = () => {
    if (!content?.next) return;
    if (userId && !readChapters.includes(content.position)) toggleRead(content.position, true);
    goTo(content.next);
  };

  const onTextSelected = () => {
    if (!userId) return;
    const pending = pendingNoteFromSelection("p");
    if (pending) setPendingNote(pending);
  };

  const saveNote = async (noteText: string, stance: string | null) => {
    if (!pendingNote || !noteText) return;
    const ok = await createNote({
      anchor_quote: pendingNote.quote,
      anchor_prefix: pendingNote.prefix,
      anchor_suffix: pendingNote.suffix,
      chapter_position: position,
      note_text: noteText,
      stance,
    });
    if (ok) setPendingNote(null);
  };

  // ── Derived ──

  const chapterNotes = React.useMemo(
    () => notes.filter(n => n.chapter_position === position), [notes, position]);

  const anchoredNoteIds = React.useMemo(() => {
    if (!content) return new Set<number>();
    const normText = normalizeWs(content.text);
    return new Set(
      chapterNotes.filter(n => normText.includes(normalizeWs(n.anchor_quote))).map(n => n.id));
  }, [content, chapterNotes]);

  // ── Render ──

  const navButtons = content && (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, margin: "18px 0" }}>
      <button onClick={() => goTo(content.prev)} disabled={!content.prev}
        style={{ padding: "6px 14px", cursor: content.prev ? "pointer" : "default" }}>
        ← Poprzedni
      </button>
      <span style={{ fontSize: "0.85em", color: "#64748b", alignSelf: "center" }}>
        {content.position} / {content.chapter_total}
      </span>
      <button onClick={goNext} disabled={!content.next}
        style={{ padding: "6px 14px", cursor: content.next ? "pointer" : "default" }}>
        Następny →
      </button>
    </div>
  );

  const renderNoteRow = (n: UserNote) => (
    <NoteRow
      key={n.id}
      note={n}
      header={<>
        {STANCE_ICON[n.stance ?? ""] ?? "📝"} rozdz. {n.chapter_position ?? "?"}
        {n.chapter_position === position && !anchoredNoteIds.has(n.id) &&
          <span style={{ color: "#b45309" }}> ⚠ nie odnaleziono w tekście</span>}
      </>}
      onHeaderClick={n.chapter_position ? () => goTo(n.chapter_position) : undefined}
      onSaveText={saveNoteText}
      onDelete={deleteNote}
    />
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Czytelnik — dokument #{id}</h2>
        <button className={styles.tocToggleButton} onClick={() => setTocOpen(o => !o)}>
          📑 Spis treści ({chapters.length})
        </button>
        <NavLink to={`/chunks/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>Przegląd chunków</NavLink>
        <NavLink to="/list" style={{ fontSize: "0.85em", color: "#0369a1" }}>← Lista dokumentów</NavLink>
        <div style={{ marginLeft: "auto" }}><UserPicker identity={identity} /></div>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      {!userId && (
        <p style={{ fontSize: "0.85em", color: "#64748b", margin: "4px 0 10px" }}>
          Wybierz użytkownika, aby zapisywać postęp czytania i dodawać notatki do fragmentów.
        </p>
      )}

      <div
        className={`${styles.scrim} ${tocOpen ? styles.scrimOpen : ""}`}
        onClick={() => setTocOpen(false)}
      />

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        {/* TOC sidebar + notes */}
        <div className={`${styles.tocPanel} ${tocOpen ? styles.tocPanelOpen : ""}`}>
          <nav style={{
            background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 0",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 14px" }}>
              <strong style={{ fontSize: "0.85em" }}>Spis treści ({chapters.length})</strong>
              <button className={styles.tocClose} onClick={() => setTocOpen(false)} aria-label="Zamknij spis treści">✕</button>
            </div>
            {chapters.map(ch => {
              const isRead = readChapters.includes(ch.position);
              return (
                <div key={ch.position}
                  style={{
                    display: "flex", alignItems: "baseline", gap: 6,
                    padding: "5px 8px 5px 14px", fontSize: "0.83em", lineHeight: 1.3,
                    background: ch.position === position ? "#e0f2fe" : undefined,
                    fontWeight: ch.position === position ? 600 : undefined,
                  }}>
                  <span onClick={() => goTo(ch.position)}
                    style={{ cursor: "pointer", flex: 1, color: isRead ? "#94a3b8" : undefined }}>
                    {ch.position === position ? "▶ " : ""}{ch.position}. {ch.title}
                  </span>
                  {userId && (
                    <span
                      title={isRead ? "Oznacz jako nieprzeczytany" : "Oznacz jako przeczytany"}
                      onClick={() => toggleRead(ch.position, !isRead)}
                      style={{ cursor: "pointer", color: isRead ? "#16a34a" : "#cbd5e1" }}>
                      ✓
                    </span>
                  )}
                </div>
              );
            })}
          </nav>

          {userId && notes.length > 0 && (
            <div style={{
              background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
              marginTop: 12, padding: "10px 0",
            }}>
              <strong style={{ fontSize: "0.85em", padding: "0 14px" }}>📝 Moje notatki ({notes.length})</strong>
              {notes.map(renderNoteRow)}
            </div>
          )}
        </div>

        {/* Chapter content */}
        <div ref={contentRef} style={{ flex: 1, maxWidth: 760 }}>
          {navButtons}
          {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
          {!loading && content && (
            <article style={{ fontSize: "1.02em" }} onMouseUp={onTextSelected}>
              {renderMarkdown(content.text, chapterNotes)}
            </article>
          )}
          {navButtons}
        </div>
      </div>

      {/* Note popover */}
      {pendingNote && (
        <NotePopover pending={pendingNote} onSave={saveNote} onCancel={() => setPendingNote(null)} />
      )}
    </div>
  );
};

export default Read;
