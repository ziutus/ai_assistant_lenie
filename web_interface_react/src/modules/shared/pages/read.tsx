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

interface ReaderUser {
  id: number;
  username: string;
  display_name: string | null;
}

interface UserNote {
  id: number;
  chapter_position: number | null;
  anchor_quote: string;
  anchor_prefix: string | null;
  anchor_suffix: string | null;
  note_text: string;
  stance: string | null;
}

interface PendingNote {
  quote: string;
  prefix: string;
  suffix: string;
  x: number;
  y: number;
}

const USER_STORAGE_KEY = "lenie_userId";
const STANCE_ICON: Record<string, string> = { agree: "👍", disagree: "👎", neutral: "➖" };

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

const normalizeWs = (s: string) => s.replace(/\s+/g, " ").trim();

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
      out.push(<Tag key={i} style={{ marginTop: level === 2 ? 0 : 28 }}>{heading[2]}</Tag>);
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
  const contentRef = React.useRef<HTMLDivElement>(null);

  // ── User identity ──
  const [users, setUsers] = React.useState<ReaderUser[]>([]);
  const [userId, setUserId] = React.useState<number | null>(() => {
    const v = localStorage.getItem(USER_STORAGE_KEY);
    return v ? Number(v) : null;
  });
  const [newUsername, setNewUsername] = React.useState("");

  // ── Reading progress ──
  const [readChapters, setReadChapters] = React.useState<number[]>([]);
  const [progressLoaded, setProgressLoaded] = React.useState(false);
  const initialRedirectDone = React.useRef(false);

  // ── Notes ──
  const [notes, setNotes] = React.useState<UserNote[]>([]);
  const [pendingNote, setPendingNote] = React.useState<PendingNote | null>(null);
  const [noteText, setNoteText] = React.useState("");
  const [noteStance, setNoteStance] = React.useState<string | null>(null);
  const [editingNoteId, setEditingNoteId] = React.useState<number | null>(null);
  const [editingText, setEditingText] = React.useState("");

  const position = Number(searchParams.get("chapter") ?? 1);
  const headers = React.useMemo(() => {
    const h: Record<string, string> = { "x-api-key": apiKey ?? "" };
    if (userId) h["x-user-id"] = String(userId);
    return h;
  }, [apiKey, userId]);
  const jsonHeaders = React.useMemo(
    () => ({ ...headers, "Content-Type": "application/json" }), [headers]);

  const selectUser = (uid: number | null) => {
    setUserId(uid);
    setProgressLoaded(false);
    initialRedirectDone.current = false;
    if (uid) localStorage.setItem(USER_STORAGE_KEY, String(uid));
    else localStorage.removeItem(USER_STORAGE_KEY);
  };

  // ── Data loading ──

  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/users`, { headers: { "x-api-key": apiKey ?? "" } });
        const data = await r.json();
        if (data.status === "success") setUsers(data.users ?? []);
      } catch { /* users are optional — reader works without identity */ }
    })();
  }, [apiUrl, apiKey]);

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

  React.useEffect(() => {
    if (!userId) { setNotes([]); return; }
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${id}/notes`, { headers });
        const data = await r.json();
        if (data.status === "success") setNotes(data.notes ?? []);
      } catch { /* notes are best-effort */ }
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

  const addUser = async () => {
    const username = newUsername.trim();
    if (!username) return;
    const r = await fetch(`${apiUrl}/users`, {
      method: "POST", headers: { "x-api-key": apiKey ?? "", "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const data = await r.json();
    if (data.status === "success") {
      setUsers(prev => [...prev, data.user]);
      selectUser(data.user.id);
      setNewUsername("");
    } else {
      alert(data.message ?? "Nie udało się dodać użytkownika");
    }
  };

  const onTextSelected = () => {
    if (!userId) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;
    const quote = normalizeWs(sel.toString());
    if (quote.length < 3 || quote.length > 2000) return;

    let prefix = "";
    let suffix = "";
    const anchorEl = sel.anchorNode instanceof Element ? sel.anchorNode : sel.anchorNode?.parentElement;
    const para = anchorEl?.closest("p");
    const paraText = para?.textContent ?? "";
    const idx = paraText.indexOf(quote);
    if (idx >= 0) {
      prefix = paraText.slice(Math.max(0, idx - 50), idx);
      suffix = paraText.slice(idx + quote.length, idx + quote.length + 50);
    }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    setPendingNote({ quote, prefix, suffix, x: rect.left + window.scrollX, y: rect.bottom + window.scrollY + 6 });
    setNoteText("");
    setNoteStance(null);
  };

  const saveNote = async () => {
    if (!pendingNote || !noteText.trim()) return;
    const r = await fetch(`${apiUrl}/document/${id}/notes`, {
      method: "POST", headers: jsonHeaders,
      body: JSON.stringify({
        anchor_quote: pendingNote.quote,
        anchor_prefix: pendingNote.prefix,
        anchor_suffix: pendingNote.suffix,
        chapter_position: position,
        note_text: noteText.trim(),
        stance: noteStance,
      }),
    });
    const data = await r.json();
    if (data.status === "success") {
      setNotes(prev => [...prev, data.note]);
      setPendingNote(null);
    } else {
      alert(data.message ?? "Nie udało się zapisać notatki");
    }
  };

  const deleteNote = async (noteId: number) => {
    if (!window.confirm("Usunąć notatkę?")) return;
    const r = await fetch(`${apiUrl}/note/${noteId}`, { method: "DELETE", headers });
    const data = await r.json();
    if (data.status === "success") setNotes(prev => prev.filter(n => n.id !== noteId));
  };

  const saveEditedNote = async (noteId: number) => {
    const text = editingText.trim();
    if (!text) return;
    const r = await fetch(`${apiUrl}/note/${noteId}`, {
      method: "PATCH", headers: jsonHeaders,
      body: JSON.stringify({ note_text: text }),
    });
    const data = await r.json();
    if (data.status === "success") {
      setNotes(prev => prev.map(n => (n.id === noteId ? data.note : n)));
      setEditingNoteId(null);
    }
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

  const userPicker = (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.85em" }}>
      <span style={{ color: "#64748b" }}>Czytasz jako:</span>
      <select value={userId ?? ""} onChange={e => selectUser(e.target.value ? Number(e.target.value) : null)}>
        <option value="">— wybierz —</option>
        {users.map(u => (
          <option key={u.id} value={u.id}>{u.display_name || u.username}</option>
        ))}
      </select>
      <input
        value={newUsername} onChange={e => setNewUsername(e.target.value)}
        onKeyDown={e => e.key === "Enter" && addUser()}
        placeholder="nowy użytkownik…" style={{ width: 130 }}
      />
      <button onClick={addUser} disabled={!newUsername.trim()}>＋</button>
    </div>
  );

  const renderNoteRow = (n: UserNote, showUnanchored: boolean) => (
    <div key={n.id} style={{
      padding: "6px 10px", borderBottom: "1px solid #e2e8f0", fontSize: "0.8em", lineHeight: 1.4,
    }}>
      <div style={{ color: "#64748b", cursor: n.chapter_position ? "pointer" : undefined }}
        onClick={() => n.chapter_position && goTo(n.chapter_position)}>
        {STANCE_ICON[n.stance ?? ""] ?? "📝"} rozdz. {n.chapter_position ?? "?"}
        {showUnanchored && n.chapter_position === position && !anchoredNoteIds.has(n.id) &&
          <span style={{ color: "#b45309" }}> ⚠ nie odnaleziono w tekście</span>}
      </div>
      <div style={{ fontStyle: "italic", color: "#94a3b8", margin: "2px 0" }}>
        „{n.anchor_quote.length > 90 ? `${n.anchor_quote.slice(0, 90)}…` : n.anchor_quote}"
      </div>
      {editingNoteId === n.id ? (
        <div>
          <textarea value={editingText} onChange={e => setEditingText(e.target.value)}
            style={{ width: "100%", minHeight: 50 }} />
          <button onClick={() => saveEditedNote(n.id)}>Zapisz</button>{" "}
          <button onClick={() => setEditingNoteId(null)}>Anuluj</button>
        </div>
      ) : (
        <div>
          {n.note_text}{" "}
          <span style={{ whiteSpace: "nowrap" }}>
            <button title="Edytuj" style={{ border: "none", background: "none", cursor: "pointer" }}
              onClick={() => { setEditingNoteId(n.id); setEditingText(n.note_text); }}>✏</button>
            <button title="Usuń" style={{ border: "none", background: "none", cursor: "pointer" }}
              onClick={() => deleteNote(n.id)}>🗑</button>
          </span>
        </div>
      )}
    </div>
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 10, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Czytelnik — dokument #{id}</h2>
        <NavLink to={`/chunks/${id}`} style={{ fontSize: "0.85em", color: "#0369a1" }}>Przegląd chunków</NavLink>
        <NavLink to="/list" style={{ fontSize: "0.85em", color: "#0369a1" }}>← Lista dokumentów</NavLink>
        <div style={{ marginLeft: "auto" }}>{userPicker}</div>
      </div>

      {error && <p style={{ color: "#b91c1c" }}>{error}</p>}
      {!userId && (
        <p style={{ fontSize: "0.85em", color: "#64748b", margin: "4px 0 10px" }}>
          Wybierz użytkownika, aby zapisywać postęp czytania i dodawać notatki do fragmentów.
        </p>
      )}

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        {/* TOC sidebar + notes */}
        <div style={{ flex: "0 0 300px", position: "sticky", top: 12, maxHeight: "85vh", overflowY: "auto" }}>
          <nav style={{
            background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 0",
          }}>
            <strong style={{ fontSize: "0.85em", padding: "0 14px" }}>Spis treści ({chapters.length})</strong>
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
              {notes.map(n => renderNoteRow(n, true))}
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
        <div style={{
          position: "absolute", left: pendingNote.x, top: pendingNote.y, zIndex: 50,
          background: "#fff", border: "1px solid #cbd5e1", borderRadius: 8, padding: 10,
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)", width: 340,
        }}>
          <div style={{ fontSize: "0.75em", color: "#94a3b8", fontStyle: "italic", marginBottom: 6 }}>
            „{pendingNote.quote.length > 120 ? `${pendingNote.quote.slice(0, 120)}…` : pendingNote.quote}"
          </div>
          <textarea
            autoFocus value={noteText} onChange={e => setNoteText(e.target.value)}
            placeholder="Twoja notatka — co myślisz o tym fragmencie?"
            style={{ width: "100%", minHeight: 60, fontSize: "0.85em" }}
          />
          <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6 }}>
            {(["agree", "disagree", "neutral"] as const).map(s => (
              <button key={s} onClick={() => setNoteStance(noteStance === s ? null : s)}
                title={{ agree: "Zgadzam się", disagree: "Nie zgadzam się", neutral: "Neutralnie" }[s]}
                style={{
                  border: noteStance === s ? "2px solid #0369a1" : "1px solid #cbd5e1",
                  borderRadius: 6, background: "#fff", cursor: "pointer", padding: "2px 8px",
                }}>
                {STANCE_ICON[s]}
              </button>
            ))}
            <span style={{ marginLeft: "auto" }}>
              <button onClick={saveNote} disabled={!noteText.trim()} style={{ marginRight: 6 }}>Zapisz</button>
              <button onClick={() => setPendingNote(null)}>Anuluj</button>
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default Read;
