import React from "react";
import { useParams, useSearchParams, NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import {
  NotePopover, NoteRow, PendingNote, ReaderIdentityBadge, STANCE_ICON, UserNote,
  normalizeWs, pendingNoteFromSelection, useReaderIdentity, useUserNotes,
} from "../components/ReaderNotes/readerNotes";
import type { CountryTag, PlaceMarker } from "../components/CountryMap/countryMap";
import { EntityChips, EntityItem } from "../components/EntitiesPanel/entitiesPanel";
import { useIsDesktop } from "../hooks/useIsDesktop";
import styles from "./read.module.css";

// Lazy-loaded: leaflet (~150 kB) should not land in the main bundle for users
// who never open a geopolitical article on desktop (mobile, other pages).
const CountryMap = React.lazy(() => import("../components/CountryMap/countryMap"));

// ── Types ────────────────────────────────────────────────────────────────────

interface Chapter {
  position: number;
  level: number;
  title: string;
  length: number;
  // Present for markdown-header chapters; absent for the TEMAT-chunk fallback
  // used by documents with no H1/H2 structure (YouTube/movie transcripts).
  char_start?: number;
  char_end?: number;
}

interface ChapterContent {
  position: number;
  title: string;
  text: string;
  chapter_total: number;
  prev: number | null;
  next: number | null;
}

// Chapter-scoped sidebar data (GET /document/:id/chapter/:pos/entities) —
// document-level entities/countries filtered down to the chapter being read.
interface ChapterScope {
  persons: EntityItem[];
  placeItems: EntityItem[];
  markers: PlaceMarker[];
  countries: CountryTag[];
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

// Document types that have an editor page at /{type}/:id
const EDITOR_TYPES = new Set(["webpage", "link", "youtube", "movie", "email"]);

// ── Page ─────────────────────────────────────────────────────────────────────

const Read: React.FC = () => {
  const { id } = useParams();
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();

  const [chapters, setChapters] = React.useState<Chapter[]>([]);
  const [documentType, setDocumentType] = React.useState<string | null>(null);
  const [countries, setCountries] = React.useState<CountryTag[]>([]);
  const [places, setPlaces] = React.useState<PlaceMarker[]>([]);
  const [personItems, setPersonItems] = React.useState<EntityItem[]>([]);
  const [placeItems, setPlaceItems] = React.useState<EntityItem[]>([]);
  const [thematicTags, setThematicTags] = React.useState<string[]>([]);
  const [synthesis, setSynthesis] = React.useState<string | null>(null);
  const [content, setContent] = React.useState<ChapterContent | null>(null);
  // sidebar scope: current chapter (default) vs whole document
  const [scopeChapter, setScopeChapter] = React.useState(true);
  const [chapterScope, setChapterScope] = React.useState<ChapterScope | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [tocOpen, setTocOpen] = React.useState(false);
  const contentRef = React.useRef<HTMLDivElement>(null);
  const isDesktop = useIsDesktop();

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
        setDocumentType(data.document_type ?? null);
        setCountries(data.countries ?? []);
        setThematicTags(data.thematic_tags ?? []);
        setSynthesis(data.synthesis ?? null);
      } catch (e) {
        setError(String(e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, apiKey]);

  // verified NER places (stage 3) → point markers on the country map
  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/website_entities?id=${id}`, { headers });
        const data = await r.json();
        if (data.status !== "success") return;
        const items = [...(data.entities?.geogName ?? []), ...(data.entities?.placeName ?? [])];
        setPersonItems(data.entities?.persName ?? []);
        setPlaceItems(items);
        setPlaces(
          items
            .filter((it: any) => it.verified === true && it.lat != null && it.lon != null)
            .map((it: any) => ({ name: it.text, lat: it.lat, lon: it.lon })),
        );
      } catch {
        // encje są ozdobnikiem widoku — brak nie blokuje czytnika
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, apiKey]);

  // chapter-scoped sidebar data — refetched when the reader moves to another
  // chapter; a failure falls back to the document-level entities (scope null)
  React.useEffect(() => {
    if (!scopeChapter || !progressLoaded) return;
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/chapter/${position}/entities`, { headers });
        const data = await r.json();
        if (data.status !== "success") { setChapterScope(null); return; }
        const items = [...(data.entities?.geogName ?? []), ...(data.entities?.placeName ?? [])];
        setChapterScope({
          persons: data.entities?.persName ?? [],
          placeItems: items,
          markers: items
            .filter((it: any) => it.verified === true && it.lat != null && it.lon != null)
            .map((it: any) => ({ name: it.text, lat: it.lat, lon: it.lon })),
          countries: data.countries ?? [],
        });
      } catch {
        setChapterScope(null);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, id, position, scopeChapter, progressLoaded, apiKey]);

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

  // sidebar data in the selected scope — chapter scope falls back to
  // document-level values until the chapter fetch lands (or when it fails)
  const scoped = scopeChapter ? chapterScope : null;
  const shownPersons = scoped ? scoped.persons : personItems;
  const shownPlaceItems = scoped ? scoped.placeItems : placeItems;
  const shownMarkers = scoped ? scoped.markers : places;
  const shownCountries = scoped ? scoped.countries : countries;

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
        {documentType && EDITOR_TYPES.has(documentType) && (
          <NavLink to={`/${documentType}/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>✏️ Edytuj</NavLink>
        )}
        <NavLink to={`/chunks/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>Przegląd chunków</NavLink>
        <NavLink to="/list" style={{ fontSize: "0.85em", color: "#0369a1" }}>← Lista dokumentów</NavLink>
        <div style={{ marginLeft: "auto" }}><ReaderIdentityBadge identity={identity} /></div>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}

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

        {/* Chapter content — fixed reading width, does not grow to soak up wide-screen space.
            minWidth: 0 overrides the flex item default (min-width: auto), which would
            otherwise refuse to shrink below the article's content min-content width and
            starve the right column of the space it's supposed to grow into. */}
        <div ref={contentRef} style={{ flex: "0 1 760px", minWidth: 0 }}>
          {navButtons}
          {loading && <p style={{ color: "#64748b" }}>Ładowanie…</p>}
          {!loading && content && (
            <article style={{ fontSize: "1.02em" }} onMouseUp={onTextSelected}>
              {renderMarkdown(content.text, chapterNotes)}
            </article>
          )}
          {navButtons}
        </div>

        {/* Map + entities + tags + synthesis — desktop only */}
        {isDesktop && (countries.length > 0 || places.length > 0 || personItems.length > 0
          || placeItems.length > 0 || thematicTags.length > 0 || synthesis) && (
          <div className={styles.rightPanel}>
            <div style={{ fontSize: "0.78em", color: "#64748b", display: "flex", gap: 8, alignItems: "center" }}>
              Zakres:
              {([["rozdział", true], ["cały dokument", false]] as const).map(([label, value]) => (
                <button
                  key={label}
                  onClick={() => setScopeChapter(value)}
                  style={{
                    border: "none", background: "none", cursor: "pointer", padding: 0,
                    fontSize: "1em",
                    color: scopeChapter === value ? "#0369a1" : "#94a3b8",
                    fontWeight: scopeChapter === value ? 600 : undefined,
                    textDecoration: scopeChapter === value ? undefined : "underline",
                  }}>
                  {label}
                </button>
              ))}
            </div>

            {(shownCountries.length > 0 || shownMarkers.length > 0) && (
              <React.Suspense fallback={null}>
                <CountryMap countries={shownCountries} places={shownMarkers} />
              </React.Suspense>
            )}

            {(shownPersons.length > 0 || shownPlaceItems.length > 0) && (
              <div style={{
                background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
                padding: 10, marginTop: 12, fontSize: "0.9em",
              }}>
                <EntityChips label={"👤 Osoby"} items={shownPersons} linkPersons />
                <EntityChips label={"📍 Miejsca"} items={shownPlaceItems} />
              </div>
            )}

            {scoped && !shownPersons.length && !shownPlaceItems.length
              && !shownCountries.length && !shownMarkers.length && (
              <div style={{ fontSize: "0.8em", color: "#94a3b8", marginTop: 8 }}>
                Brak osób i miejsc w tym rozdziale.
              </div>
            )}

            {thematicTags.length > 0 && (
              <div style={{
                background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8,
                padding: 10, marginTop: 12,
              }}>
                <strong style={{ fontSize: "0.85em", display: "block", marginBottom: 8 }}>🏷️ Tagi</strong>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {thematicTags.map(tag => (
                    <span key={tag} style={{
                      fontSize: "0.78em", padding: "2px 8px", borderRadius: 999,
                      background: "#f1f5f9", color: "#334155",
                    }}>
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {synthesis && (
              <details className={styles.synthesisPanel} open>
                <summary>📄 Streszczenie</summary>
                <div style={{ fontSize: "0.85em", lineHeight: 1.55, whiteSpace: "pre-wrap", marginTop: 8 }}>
                  {synthesis}
                </div>
              </details>
            )}
          </div>
        )}
      </div>

      {/* Note popover */}
      {pendingNote && (
        <NotePopover pending={pendingNote} onSave={saveNote} onCancel={() => setPendingNote(null)} />
      )}
    </div>
  );
};

export default Read;
