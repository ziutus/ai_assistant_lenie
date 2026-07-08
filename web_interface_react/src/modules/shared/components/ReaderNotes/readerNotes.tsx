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

export const USER_STORAGE_KEY = "lenie_userId";
export const STANCE_ICON: Record<string, string> = { agree: "👍", disagree: "👎", neutral: "➖" };

export const normalizeWs = (s: string) => s.replace(/\s+/g, " ").trim();

// ── Identity ─────────────────────────────────────────────────────────────────

export interface ReaderIdentity {
  users: ReaderUser[];
  userId: number | null;
  selectUser: (uid: number | null) => void;
  newUsername: string;
  setNewUsername: (v: string) => void;
  addUser: () => Promise<void>;
  headers: Record<string, string>;
  jsonHeaders: Record<string, string>;
}

export function useReaderIdentity(
  apiUrl: string,
  apiKey: string | undefined,
  onUserChange?: (uid: number | null) => void,
): ReaderIdentity {
  const [users, setUsers] = React.useState<ReaderUser[]>([]);
  const [userId, setUserId] = React.useState<number | null>(() => {
    const v = localStorage.getItem(USER_STORAGE_KEY);
    return v ? Number(v) : null;
  });
  const [newUsername, setNewUsername] = React.useState("");

  const headers = React.useMemo(() => {
    const h: Record<string, string> = { "x-api-key": apiKey ?? "" };
    if (userId) h["x-user-id"] = String(userId);
    return h;
  }, [apiKey, userId]);
  const jsonHeaders = React.useMemo(
    () => ({ ...headers, "Content-Type": "application/json" }), [headers]);

  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${apiUrl}/users`, { headers: { "x-api-key": apiKey ?? "" } });
        const data = await r.json();
        if (data.status === "success") setUsers(data.users ?? []);
      } catch { /* users are optional — pages work without identity */ }
    })();
  }, [apiUrl, apiKey]);

  const selectUser = (uid: number | null) => {
    setUserId(uid);
    if (uid) localStorage.setItem(USER_STORAGE_KEY, String(uid));
    else localStorage.removeItem(USER_STORAGE_KEY);
    onUserChange?.(uid);
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

  return { users, userId, selectUser, newUsername, setNewUsername, addUser, headers, jsonHeaders };
}

export const UserPicker: React.FC<{ identity: ReaderIdentity; label?: string }> = ({
  identity, label = "Czytasz jako:",
}) => {
  const { users, userId, selectUser, newUsername, setNewUsername, addUser } = identity;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.85em" }}>
      <span style={{ color: "#64748b" }}>{label}</span>
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
  onSave: (noteText: string, stance: string | null) => void;
  onCancel: () => void;
}> = ({ pending, onSave, onCancel }) => {
  const [noteText, setNoteText] = React.useState("");
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
          <button onClick={() => onSave(noteText.trim(), stance)} disabled={!noteText.trim()}
            style={{ marginRight: 6 }}>Zapisz</button>
          <button onClick={onCancel}>Anuluj</button>
        </span>
      </div>
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
