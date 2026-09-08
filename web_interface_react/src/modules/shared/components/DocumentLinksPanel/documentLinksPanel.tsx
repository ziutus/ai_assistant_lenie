import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";

// Typed, directed links between two library documents (backend:
// GET/POST /document/:id/links, PATCH/DELETE /document_links/:id,
// POST /document/:id/links/detect — table document_links).

interface LinkedDocumentBrief {
  id: number;
  title: string;
  url: string;
  document_type: string;
  byline: string | null;
  published_on: string | null;
}

export interface DocumentLinkItem {
  id: number;
  relation: string;
  status: "proposed" | "confirmed" | "rejected";
  detection_method: "manual" | "url_mention" | "llm";
  note: string | null;
  direction: "outgoing" | "incoming";
  label: string;
  other_document?: LinkedDocumentBrief;
}

interface RelationOption {
  value: string;
  forward_label: string;
  backward_label: string;
}

interface SearchHit {
  document_id?: number;
  id?: number;
  title?: string;
  url?: string;
  document_type?: string;
}

const TYPE_ICON: Record<string, string> = {
  link: "🔗",
  webpage: "📄",
  youtube: "▶️",
  movie: "🎬",
  social_media_post: "💬",
  email: "✉️",
  text: "📝",
  text_message: "💌",
  obsidian_note: "🗂️",
};

const editorPath = (doc: LinkedDocumentBrief) => {
  const byType: Record<string, string> = {
    link: `/link/${doc.id}`,
    webpage: `/webpage/${doc.id}`,
    text: `/text/${doc.id}`,
    youtube: `/youtube/${doc.id}`,
    movie: `/movie/${doc.id}`,
    email: `/email/${doc.id}`,
    social_media_post: `/social_media_post/${doc.id}`,
  };
  return byType[doc.document_type] ?? `/read/${doc.id}`;
};

interface Props {
  docId: number | string;
  /** Compact single-column layout for the reader sidebar. */
  compact?: boolean;
}

const DocumentLinksPanel: React.FC<Props> = ({ docId, compact = false }) => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const jsonHeaders = React.useMemo(
    () => ({ "Content-Type": "application/json", "x-api-key": `${apiKey}` }),
    [apiKey],
  );

  const [links, setLinks] = React.useState<DocumentLinkItem[]>([]);
  const [relations, setRelations] = React.useState<RelationOption[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [open, setOpen] = React.useState(!compact);

  const [showAdd, setShowAdd] = React.useState(false);
  const [targetId, setTargetId] = React.useState("");
  const [relation, setRelation] = React.useState("discusses");
  const [direction, setDirection] = React.useState<"outgoing" | "incoming">("outgoing");
  const [note, setNote] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [hits, setHits] = React.useState<SearchHit[]>([]);

  const load = React.useCallback(async () => {
    if (!docId) return;
    setLoading(true);
    setError("");
    try {
      const response = await axios.get(`${apiUrl}/document/${docId}/links`, {
        headers: { "x-api-key": `${apiKey}` },
      });
      setLinks(response.data.links ?? []);
      setRelations(response.data.relations ?? []);
    } catch (err: any) {
      setError(err.response?.data?.message || err.message || "Nie udało się pobrać powiązań.");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, apiKey, docId]);

  React.useEffect(() => {
    load().then(() => null);
  }, [load]);

  const runSearch = async () => {
    if (!query.trim()) return;
    setBusy(true);
    try {
      const response = await axios.post(
        `${apiUrl}/search`,
        { natural_query: query.trim(), limit: 8 },
        { headers: jsonHeaders },
      );
      setHits(response.data.results ?? []);
    } catch (err: any) {
      setError(err.response?.data?.message || "Wyszukiwanie nie powiodło się.");
    } finally {
      setBusy(false);
    }
  };

  const createLink = async () => {
    const parsed = Number(targetId);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      setError("Podaj poprawny identyfikator dokumentu docelowego.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await axios.post(
        `${apiUrl}/document/${docId}/links`,
        { to_document_id: parsed, relation, direction, note: note.trim() || undefined },
        { headers: jsonHeaders },
      );
      setShowAdd(false);
      setTargetId("");
      setNote("");
      setQuery("");
      setHits([]);
      await load();
    } catch (err: any) {
      setError(err.response?.data?.message || "Nie udało się utworzyć powiązania.");
    } finally {
      setBusy(false);
    }
  };

  const decide = async (linkId: number, status: "confirmed" | "rejected") => {
    setBusy(true);
    try {
      await axios.patch(`${apiUrl}/document_links/${linkId}`, { status }, { headers: jsonHeaders });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const removeLink = async (linkId: number) => {
    if (!window.confirm("Usunąć to powiązanie?")) return;
    setBusy(true);
    try {
      await axios.delete(`${apiUrl}/document_links/${linkId}`, { headers: jsonHeaders });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const detect = async () => {
    setBusy(true);
    setError("");
    try {
      const response = await axios.post(
        `${apiUrl}/document/${docId}/links/detect`,
        {},
        { headers: jsonHeaders },
      );
      await load();
      if ((response.data.created_count ?? 0) === 0) {
        setError("Nie znaleziono wzmianek URL prowadzących do innych dokumentów.");
      }
    } catch (err: any) {
      setError(err.response?.data?.message || "Wykrywanie nie powiodło się.");
    } finally {
      setBusy(false);
    }
  };

  const confirmed = links.filter((item) => item.status === "confirmed");
  const proposed = links.filter((item) => item.status === "proposed");

  const renderLink = (item: DocumentLinkItem) => {
    const other = item.other_document;
    return (
      <li key={item.id} style={{ marginBottom: 6, lineHeight: 1.4 }}>
        <span style={{ color: "#64748b", fontSize: "0.85em" }}>
          {item.direction === "incoming" ? "⬅ " : "➡ "}
          {item.label}:
        </span>{" "}
        {other ? (
          <>
            <span title={other.document_type}>{TYPE_ICON[other.document_type] ?? "•"}</span>{" "}
            <Link to={editorPath(other)}>{other.title}</Link>
            {other.byline && (
              <span style={{ color: "#94a3b8", fontSize: "0.82em" }}> — {other.byline}</span>
            )}
            <a
              href={other.url}
              target="_blank"
              rel="noreferrer"
              style={{ marginLeft: 6, fontSize: "0.8em" }}
              title="Otwórz oryginał"
            >
              ↗
            </a>
          </>
        ) : (
          <em>dokument usunięty</em>
        )}
        {item.detection_method === "url_mention" && (
          <span style={{ marginLeft: 6, fontSize: "0.75em", color: "#a16207" }}>auto</span>
        )}
        {item.note && (
          <div style={{ color: "#475569", fontSize: "0.82em", marginLeft: 16 }}>{item.note}</div>
        )}
        <span style={{ marginLeft: 8 }}>
          {item.status === "proposed" && (
            <>
              <button type="button" className="button" style={btnMini} disabled={busy}
                onClick={() => decide(item.id, "confirmed")}>
                ✓ potwierdź
              </button>{" "}
              <button type="button" className="button" style={btnMini} disabled={busy}
                onClick={() => decide(item.id, "rejected")}>
                ✕ odrzuć
              </button>
            </>
          )}
          {item.status === "confirmed" && (
            <button type="button" className="button" style={btnMini} disabled={busy}
              onClick={() => removeLink(item.id)}>
              usuń
            </button>
          )}
        </span>
      </li>
    );
  };

  return (
    <section style={{
      marginTop: 14, padding: compact ? 10 : 14, border: "1px solid #e2e8f0",
      borderRadius: 8, background: "#f8fafc",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: compact ? "pointer" : "default" }}
        onClick={() => compact && setOpen((value) => !value)}>
        <strong style={{ color: "#334155" }}>
          🔗 Powiązane dokumenty{confirmed.length ? ` (${confirmed.length})` : ""}
          {proposed.length ? <span style={{ color: "#a16207" }}> · {proposed.length} do przeglądu</span> : null}
        </strong>
        {compact && <span style={{ marginLeft: "auto" }}>{open ? "▲" : "▼"}</span>}
      </div>

      {open && (
        <div style={{ marginTop: 10 }}>
          {loading && <div style={{ color: "#64748b" }}>Wczytywanie…</div>}
          {error && <div style={{ color: "#b91c1c", fontSize: "0.85em", marginBottom: 6 }}>{error}</div>}

          {!loading && links.length === 0 && (
            <div style={{ color: "#64748b", fontSize: "0.88em" }}>Brak powiązań.</div>
          )}

          {links.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 8px" }}>
              {proposed.map(renderLink)}
              {confirmed.map(renderLink)}
              {links.filter((i) => i.status === "rejected").map(renderLink)}
            </ul>
          )}

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="button" style={btnMini} disabled={busy}
              onClick={() => setShowAdd((value) => !value)}>
              {showAdd ? "Anuluj" : "+ Powiąż z dokumentem"}
            </button>
            <button type="button" className="button" style={btnMini} disabled={busy} onClick={detect}>
              Wykryj z linków w treści
            </button>
          </div>

          {showAdd && (
            <div style={{
              marginTop: 10, padding: 10, border: "1px solid #cbd5e1", borderRadius: 6, background: "#fff",
            }}>
              <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                <input
                  type="text"
                  placeholder="Szukaj dokumentu…"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); runSearch(); } }}
                  style={{ flex: "1 1 200px" }}
                />
                <button type="button" className="button" style={btnMini} disabled={busy} onClick={runSearch}>
                  Szukaj
                </button>
              </div>
              {hits.length > 0 && (
                <ul style={{ listStyle: "none", padding: 0, margin: "0 0 8px", maxHeight: 160, overflowY: "auto" }}>
                  {hits.map((hit) => {
                    const hid = hit.document_id ?? hit.id;
                    return (
                      <li key={hid} style={{ marginBottom: 3 }}>
                        <button
                          type="button"
                          className="button"
                          style={{ ...btnMini, textAlign: "left" }}
                          onClick={() => setTargetId(String(hid))}
                        >
                          #{hid} {TYPE_ICON[hit.document_type ?? ""] ?? ""} {hit.title || hit.url}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <label style={{ fontSize: "0.85em" }}>
                  ID dokumentu:{" "}
                  <input
                    type="number"
                    value={targetId}
                    onChange={(event) => setTargetId(event.target.value)}
                    style={{ width: 90 }}
                  />
                </label>
                <select value={direction} onChange={(event) => setDirection(event.target.value as any)}>
                  <option value="outgoing">ten dokument →</option>
                  <option value="incoming">→ ten dokument</option>
                </select>
                <select value={relation} onChange={(event) => setRelation(event.target.value)}>
                  {relations.map((option) => (
                    <option key={option.value} value={option.value}>
                      {direction === "outgoing" ? option.forward_label : option.backward_label}
                    </option>
                  ))}
                </select>
              </div>
              <input
                type="text"
                placeholder="Notatka (opcjonalnie)"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                style={{ width: "100%", marginTop: 8 }}
              />
              <div style={{ marginTop: 8 }}>
                <button type="button" className="button" style={btnMini} disabled={busy} onClick={createLink}>
                  Zapisz powiązanie
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
};

const btnMini: React.CSSProperties = { fontSize: "0.8em", padding: "2px 8px" };

export default DocumentLinksPanel;
