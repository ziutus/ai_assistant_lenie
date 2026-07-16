import React from "react";

// Shared reader-identity and fragment-note building blocks (Etap 7, iter. 2).
// Used by the reader (/read/:id) and the chunk review (/chunks/:id).

// ── Types ────────────────────────────────────────────────────────────────────

export interface ReaderUser {
  id: number;
  username: string;
  display_name: string | null;
}

export interface UserNote {
  id: number;
  user_id: number;
  document_id: number;
  chapter_position: number | null;
  anchor_quote: string;
  anchor_prefix: string | null;
  anchor_suffix: string | null;
  run_id: number | null;
  chunk_id: number | null;
  note_text: string;
  tags: string[];
  stance: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PendingNote {
  quote: string;
  prefix: string;
  suffix: string;
  x: number;
  y: number;
}

// Legacy localStorage key from the pre-Etap-8 user picker; identity now comes
// exclusively from the API key, so any leftover value is stale and ignored.
const LEGACY_USER_STORAGE_KEY = "lenie_userId";

export const STANCE_ICON: Record<string, string> = { agree: "👍", disagree: "👎", neutral: "➖" };

export const normalizeWs = (s: string) => s.replace(/\s+/g, " ").trim();

// ── Identity ─────────────────────────────────────────────────────────────────
// Etap 8: reader identity is resolved from GET /whoami (which reflects the
// presented API key). A "user" key carries the reader's identity outright —
// no selector, no x-user-id header. A "service"/legacy key has no reader
// identity at all: the reading-progress/notes endpoints 403 for it, so the
// pages must not call them (gated by `userId === null` below).

export type ReaderKind = "user" | "service" | null;

export interface ReaderIdentity {
  kind: ReaderKind;
  keyName: string | null;
  isLegacy: boolean;
  user: ReaderUser | null;
  userId: number | null;
  loading: boolean;
  error: string | null;
  headers: Record<string, string>;
  jsonHeaders: Record<string, string>;
}

export function useReaderIdentity(
  apiUrl: string,
  apiKey: string | undefined,
  onUserChange?: (uid: number | null) => void,
): ReaderIdentity {
  const [kind, setKind] = React.useState<ReaderKind>(null);
  const [keyName, setKeyName] = React.useState<string | null>(null);
  const [isLegacy, setIsLegacy] = React.useState(false);
  const [user, setUser] = React.useState<ReaderUser | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);
  const jsonHeaders = React.useMemo(
    () => ({ ...headers, "Content-Type": "application/json" }), [headers]);

  React.useEffect(() => {
    localStorage.removeItem(LEGACY_USER_STORAGE_KEY);
  }, []);

  React.useEffect(() => {
    if (!apiKey) { setLoading(false); return; }
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/whoami`, { headers: { "x-api-key": apiKey } });
        const data = await r.json();
        if (data.status !== "success") throw new Error(data.message ?? "Nie udało się ustalić tożsamości");
        setKind(data.kind ?? null);
        setKeyName(data.key_name ?? null);
        setIsLegacy(Boolean(data.is_legacy));
        setUser(data.user ?? null);
      } catch (e) {
        setKind(null);
        setUser(null);
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [apiUrl, apiKey]);

  const userId = kind === "user" ? (user?.id ?? null) : null;

  const prevUserId = React.useRef<number | null>(null);
  React.useEffect(() => {
    if (prevUserId.current !== userId) {
      prevUserId.current = userId;
      onUserChange?.(userId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  return { kind, keyName, isLegacy, user, userId, loading, error, headers, jsonHeaders };
}

// "TypeError: Failed to fetch" (Chrome/Edge) / "NetworkError when attempting
// to fetch resource" (Firefox) means the browser could not even open a
// connection — almost always a local network problem (tryb samolotowy, WiFi,
// VPN), not a backend or API-key issue. Anything else is a real backend
// error (bad key, 500, unexpected response shape).
function friendlyIdentityError(error: string): string {
  if (/Failed to fetch|NetworkError|Load failed/i.test(error)) {
    return "Brak połączenia z serwerem — sprawdź internet/Wi-Fi (np. czy nie jest włączony tryb samolotowy) i czy adres backendu jest osiągalny.";
  }
  return `Błąd tożsamości klucza API: ${error}`;
}

/** Read-only reader-identity indicator — replaces the old user-picker/add-user
 *  UI (Etap 8, iter. 2): identity comes from the key, there is nothing to
 *  choose. For non-user keys it explains why progress/notes are absent. */
export const ReaderIdentityBadge: React.FC<{ identity: ReaderIdentity }> = ({ identity }) => {
  const { kind, user, loading, error } = identity;
  if (loading) return null;
  if (error) {
    return <span style={{ fontSize: "0.8em", color: "#b91c1c" }}>{friendlyIdentityError(error)}</span>;
  }
  if (kind === "user") {
    return (
      <span style={{ fontSize: "0.85em", color: "#64748b" }}>
        Czytasz jako: <strong>{user?.display_name || user?.username}</strong>
      </span>
    );
  }
  return (
    <span style={{ fontSize: "0.8em", color: "#94a3b8" }}>
      Ten klucz API nie ma tożsamości czytelnika — postęp czytania i notatki są niedostępne
    </span>
  );
};

// ── Notes CRUD ───────────────────────────────────────────────────────────────

export interface NotesApi {
  notes: UserNote[];
  createNote: (payload: {
    anchor_quote: string;
    anchor_prefix: string;
    anchor_suffix: string;
    chapter_position: number | null;
    run_id?: number | null;
    chunk_id?: number | null;
    note_text: string;
    tags?: string[];
    stance: string | null;
  }) => Promise<boolean>;
  saveNoteText: (noteId: number, text: string) => Promise<boolean>;
  deleteNote: (noteId: number) => Promise<void>;
}

export function useUserNotes(
  apiUrl: string,
  docId: string | undefined,
  identity: ReaderIdentity,
): NotesApi {
  const { userId, headers, jsonHeaders } = identity;
  const [notes, setNotes] = React.useState<UserNote[]>([]);

  React.useEffect(() => {
    if (!userId || !docId) { setNotes([]); return; }
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/document/${docId}/notes`, { headers });
        const data = await r.json();
        if (data.status === "success") setNotes(data.notes ?? []);
      } catch { /* notes are best-effort */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl, docId, userId]);

  const createNote: NotesApi["createNote"] = async payload => {
    const r = await fetch(`${apiUrl}/document/${docId}/notes`, {
      method: "POST", headers: jsonHeaders, body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (data.status === "success") {
      setNotes(prev => [...prev, data.note]);
      return true;
    }
    alert(data.message ?? "Nie udało się zapisać notatki");
    return false;
  };

  const saveNoteText: NotesApi["saveNoteText"] = async (noteId, text) => {
    const r = await fetch(`${apiUrl}/note/${noteId}`, {
      method: "PATCH", headers: jsonHeaders, body: JSON.stringify({ note_text: text }),
    });
    const data = await r.json();
    if (data.status === "success") {
      setNotes(prev => prev.map(n => (n.id === noteId ? data.note : n)));
      return true;
    }
    return false;
  };

  const deleteNote: NotesApi["deleteNote"] = async noteId => {
    if (!window.confirm("Usunąć notatkę?")) return;
    const r = await fetch(`${apiUrl}/note/${noteId}`, { method: "DELETE", headers });
    const data = await r.json();
    if (data.status === "success") setNotes(prev => prev.filter(n => n.id !== noteId));
  };

  return { notes, createNote, saveNoteText, deleteNote };
}

// ── Selection → pending note ─────────────────────────────────────────────────

/** Build a PendingNote from the current text selection, or null when there is
 *  no usable selection. Prefix/suffix come from the nearest block element. */
export function pendingNoteFromSelection(blockSelector = "p"): PendingNote | null {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) return null;
  const quote = normalizeWs(sel.toString());
  if (quote.length < 3 || quote.length > 2000) return null;

  let prefix = "";
  let suffix = "";
  const anchorEl = sel.anchorNode instanceof Element ? sel.anchorNode : sel.anchorNode?.parentElement;
  const block = anchorEl?.closest(blockSelector);
  const blockText = block?.textContent ?? "";
  const idx = blockText.indexOf(quote);
  if (idx >= 0) {
    prefix = blockText.slice(Math.max(0, idx - 50), idx);
    suffix = blockText.slice(idx + quote.length, idx + quote.length + 50);
  }
  const rect = sel.getRangeAt(0).getBoundingClientRect();
  return { quote, prefix, suffix, x: rect.left + window.scrollX, y: rect.bottom + window.scrollY + 6 };
}

// ── UI: note popover (absolute-positioned at the selection) ──────────────────

export const NotePopover: React.FC<{
  pending: PendingNote;
  onSave: (noteText: string, stance: string | null, tags: string[]) => void;
  onSearch?: (quote: string) => void;
  onCancel: () => void;
}> = ({ pending, onSave, onSearch, onCancel }) => {
  const [noteText, setNoteText] = React.useState("");
  const [tagText, setTagText] = React.useState("");
  const [stance, setStance] = React.useState<string | null>(null);
  return (
    <div style={{
      position: "absolute", left: pending.x, top: pending.y, zIndex: 50,
      background: "#fff", border: "1px solid #cbd5e1", borderRadius: 8, padding: 10,
      boxShadow: "0 4px 12px rgba(0,0,0,0.15)", width: 340,
    }}>
      <div style={{ fontSize: "0.75em", color: "#94a3b8", fontStyle: "italic", marginBottom: 6 }}>
        „{pending.quote.length > 120 ? `${pending.quote.slice(0, 120)}…` : pending.quote}"
      </div>
      <textarea
        autoFocus value={noteText} onChange={e => setNoteText(e.target.value)}
        placeholder="Twoja notatka — co myślisz o tym fragmencie?"
        style={{ width: "100%", minHeight: 60, fontSize: "0.85em" }}
      />
      <input
        value={tagText} onChange={e => setTagText(e.target.value)}
        placeholder="Tagi, np. ESSI (oddziel przecinkami)"
        style={{ width: "100%", marginTop: 6, fontSize: "0.85em" }}
      />
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6 }}>
        {(["agree", "disagree", "neutral"] as const).map(s => (
          <button key={s} onClick={() => setStance(stance === s ? null : s)}
            title={{ agree: "Zgadzam się", disagree: "Nie zgadzam się", neutral: "Neutralnie" }[s]}
            style={{
              border: stance === s ? "2px solid #0369a1" : "1px solid #cbd5e1",
              borderRadius: 6, background: "#fff", cursor: "pointer", padding: "2px 8px",
            }}>
            {STANCE_ICON[s]}
          </button>
        ))}
        <span style={{ marginLeft: "auto" }}>
          <button onClick={() => onSave(noteText.trim(), stance,
            tagText.split(",").map(t => t.trim()).filter(Boolean))}
            disabled={!noteText.trim() && !tagText.trim()}
            style={{ marginRight: 6 }}>Zapisz</button>
          <button onClick={onCancel}>Anuluj</button>
        </span>
      </div>
      {onSearch && (
        <button type="button" onClick={() => onSearch(pending.quote)} style={{ marginTop: 8, width: "100%" }}>
          🔎 Szukaj tego fragmentu w bazie Lenie
        </button>
      )}
    </div>
  );
};

// ── UI: single note row with inline edit/delete ──────────────────────────────

export const NoteRow: React.FC<{
  note: UserNote;
  header: React.ReactNode;
  onHeaderClick?: () => void;
  onSaveText: (noteId: number, text: string) => Promise<boolean>;
  onDelete: (noteId: number) => void;
}> = ({ note, header, onHeaderClick, onSaveText, onDelete }) => {
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState("");
  return (
    <div style={{
      padding: "6px 10px", borderBottom: "1px solid #e2e8f0", fontSize: "0.8em", lineHeight: 1.4,
    }}>
      <div style={{ color: "#64748b", cursor: onHeaderClick ? "pointer" : undefined }}
        onClick={onHeaderClick}>
        {header}
      </div>
      <div style={{ fontStyle: "italic", color: "#94a3b8", margin: "2px 0" }}>
        „{note.anchor_quote.length > 90 ? `${note.anchor_quote.slice(0, 90)}…` : note.anchor_quote}"
      </div>
      {(note.tags?.length ?? 0) > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "3px 0" }}>
          {note.tags.map(tag => <span key={tag} style={{ color: "#0369a1" }}>#{tag}</span>)}
        </div>
      )}
      {editing ? (
        <div>
          <textarea value={text} onChange={e => setText(e.target.value)}
            style={{ width: "100%", minHeight: 50 }} />
          <button onClick={async () => { if (await onSaveText(note.id, text.trim())) setEditing(false); }}
            disabled={!text.trim()}>Zapisz</button>{" "}
          <button onClick={() => setEditing(false)}>Anuluj</button>
        </div>
      ) : (
        <div>
          {note.note_text}{" "}
          <span style={{ whiteSpace: "nowrap" }}>
            <button title="Edytuj" style={{ border: "none", background: "none", cursor: "pointer" }}
              onClick={() => { setEditing(true); setText(note.note_text); }}>✏</button>
            <button title="Usuń" style={{ border: "none", background: "none", cursor: "pointer" }}
              onClick={() => onDelete(note.id)}>🗑</button>
          </span>
        </div>
      )}
    </div>
  );
};
