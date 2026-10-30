import React from "react";
import { Link } from "react-router-dom";

type Props = {
  apiUrl: string;
  headers: Record<string, string>;
  // Stored as the radar entry's source_context, e.g. "WhatsApp: Sąsiedzi".
  sourceContext: string;
  children: React.ReactNode;
};

type Menu = { x: number; y: number; name: string; context: string };
type Outcome = { kind: "created" | "existing"; id: number; name: string } | { kind: "error"; text: string };

// Wraps a block of text: a right click on selected text opens a small menu that puts the selection on the
// tool radar (status "watchlist"). Without a selection the browser menu stays.
export default function RadarSelectionMenu({ apiUrl, headers, sourceContext, children }: Props) {
  const [menu, setMenu] = React.useState<Menu | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [outcome, setOutcome] = React.useState<Outcome | null>(null);

  const close = React.useCallback(() => { setMenu(null); setOutcome(null); }, []);

  React.useEffect(() => {
    if (!menu) return undefined;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menu, close]);

  const onContextMenu = (event: React.MouseEvent<HTMLElement>) => {
    const selected = window.getSelection()?.toString().replace(/\s+/g, " ").trim() ?? "";
    if (!selected) return;
    event.preventDefault();
    const node = window.getSelection()?.anchorNode;
    const block = (node instanceof Element ? node : node?.parentElement)?.closest("[data-radar-context]");
    setOutcome(null);
    setMenu({
      x: event.clientX, y: event.clientY, name: selected.slice(0, 255),
      context: block?.getAttribute("data-radar-context") || "",
    });
  };

  const add = async () => {
    if (!menu || !menu.name.trim()) return;
    setBusy(true);
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations`, {
        method: "POST", headers,
        body: JSON.stringify({
          name: menu.name.trim(), status: "watchlist",
          source_context: menu.context ? `${sourceContext} — ${menu.context}` : sourceContext,
        }),
      });
      if (!response.ok) throw new Error(`Nie udało się dodać (HTTP ${response.status})`);
      const body = await response.json();
      const existing = body.existing_tool_recommendation ?? body.existing_tool;
      setOutcome(existing
        ? { kind: "existing", id: existing.id, name: existing.name }
        : { kind: "created", id: body.tool_recommendation.id, name: body.tool_recommendation.name });
    } catch (cause) {
      setOutcome({ kind: "error", text: cause instanceof Error ? cause.message : "Nie udało się dodać do radaru" });
    } finally { setBusy(false); }
  };

  return (
    <div onContextMenu={onContextMenu}>
      {children}
      {menu && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 999 }} onMouseDown={close} onContextMenu={(e) => { e.preventDefault(); close(); }} />
          <div role="dialog" aria-label="Dodaj do radaru" style={{
            position: "fixed", left: Math.min(menu.x, window.innerWidth - 320), top: Math.min(menu.y, window.innerHeight - 170),
            zIndex: 1000, width: 300, background: "#fff", border: "1px solid #ccd", borderRadius: 6,
            boxShadow: "0 4px 14px rgba(0,0,0,.25)", padding: 10, fontSize: ".9rem",
          }}>
            {outcome?.kind === "created" && (
              <p>✓ Dodano „{outcome.name}” do radaru (<Link to={`/tool-recommendations?tool=${outcome.id}`}>otwórz</Link>).</p>
            )}
            {outcome?.kind === "existing" && (
              <p>„{outcome.name}” jest już w katalogu lub na radarze (<Link to={`/tool-recommendations?tool=${outcome.id}`}>otwórz</Link>).</p>
            )}
            {outcome?.kind === "error" && <p role="alert" style={{ color: "#b91c1c" }}>{outcome.text}</p>}
            {(!outcome || outcome.kind === "error") && (
              <>
                <label style={{ display: "block", marginBottom: 6 }}>
                  Nazwa narzędzia
                  <input style={{ width: "100%", boxSizing: "border-box" }} value={menu.name} maxLength={255}
                    onChange={(e) => setMenu({ ...menu, name: e.target.value })} />
                </label>
                <button type="button" className="button" disabled={busy || !menu.name.trim()} onClick={() => void add()}>
                  {busy ? "Dodaję…" : "📡 Dodaj do radaru"}
                </button>{" "}
                <button type="button" className="button" onClick={() => { void navigator.clipboard?.writeText(menu.name); close(); }}>
                  📋 Kopiuj
                </button>
              </>
            )}
            {outcome && outcome.kind !== "error" && (
              <button type="button" className="button" onClick={close}>Zamknij</button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
