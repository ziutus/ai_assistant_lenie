import React from "react";

export type FocusStatus = "watchlist" | "compare" | "testing" | "adopted" | "rejected" | "archived";

type PeerRadar = {
  id: number; name: string; status: FocusStatus; category: string | null; description: string | null;
  homepage_url: string | null; personal_note: string | null;
  github: { stars: number | null; pushed_at: string | null; archived: boolean } | null;
};
type PeerTool = {
  id: number; name: string; homepage_url: string | null; personal_notes: string | null;
  pricing: string | null; license: string | null;
};
type Peers = { category: string | null; radar: PeerRadar[]; tools: PeerTool[] };

const statusLabel: Record<FocusStatus, string> = {
  watchlist: "Nieocenione", compare: "Do porównania", testing: "Testowane",
  adopted: "Używam", rejected: "Odrzucone", archived: "Archiwum",
};
// Tools in use come first: the candidate is judged against what is already running.
const statusOrder: Record<FocusStatus, number> = { adopted: 0, testing: 1, compare: 2, watchlist: 3, rejected: 4, archived: 5 };
const badgeStyle = (adopted: boolean) => ({
  background: adopted ? "#dcfce7" : "#e2e8f0", color: adopted ? "#166534" : "#334155",
  borderRadius: 4, padding: "2px 6px", fontSize: ".75rem", marginLeft: 8,
});

type Props = {
  apiUrl: string;
  headers: Record<string, string>;
  itemId: number;
  itemName: string;
  initialNote: string | null;
  position: number;
  total: number;
  busy: boolean;
  actions: Array<[FocusStatus, string, string]>;
  details: React.ReactNode;
  onDecide: (status: FocusStatus, note: string | null) => void;
  onOpenPeer: (id: number) => void;
  onChanged: () => void;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
};

export default function ToolFocusReview({
  apiUrl, headers, itemId, itemName, initialNote, position, total, busy, actions, details,
  onDecide, onOpenPeer, onChanged, onPrev, onNext, onClose,
}: Props) {
  const [peers, setPeers] = React.useState<Peers | null>(null);
  const [peersError, setPeersError] = React.useState("");
  const [reloadKey, setReloadKey] = React.useState(0);
  const [peerBusy, setPeerBusy] = React.useState<number | null>(null);
  const [note, setNote] = React.useState(initialNote ?? "");

  React.useEffect(() => { setNote(initialNote ?? ""); }, [itemId, initialNote]);

  React.useEffect(() => {
    let cancelled = false;
    setPeers(null); setPeersError("");
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/tool_recommendations/${itemId}/peers`, { headers });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(String(data.message || "Nie udało się pobrać alternatyw"));
        if (!cancelled) setPeers(data as Peers);
      } catch (cause) {
        if (!cancelled) setPeersError(cause instanceof Error ? cause.message : "Nie udało się pobrać alternatyw");
      }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, headers, itemId, reloadKey]);

  // Quick decision on a neighbour from the same category, without leaving this card.
  const movePeer = async (peerId: number, status: FocusStatus) => {
    setPeerBusy(peerId); setPeersError("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/${peerId}/status`, { method: "POST", headers, body: JSON.stringify({ status }) });
      if (!response.ok) throw new Error("Nie udało się zmienić statusu narzędzia");
      setReloadKey(current => current + 1);
      onChanged();
    } catch (cause) {
      setPeersError(cause instanceof Error ? cause.message : "Nie udało się zmienić statusu narzędzia");
    } finally { setPeerBusy(null); }
  };

  const radar = peers ? [...peers.radar].sort((a, b) => statusOrder[a.status] - statusOrder[b.status] || a.name.localeCompare(b.name)) : [];
  const trimmedNote = note.trim();
  const noteChanged = trimmedNote !== (initialNote ?? "").trim();

  return <div>
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
      {position > 0 ? <>
        <button type="button" onClick={onPrev} disabled={position <= 1 || busy}>← Poprzednie</button>
        <strong aria-live="polite">{position} / {total}</strong>
        <button type="button" onClick={onNext} disabled={position >= total || busy}>Następne →</button>
      </> : <span style={{ color: "#64748b" }}>Narzędzie spoza bieżącej zakładki</span>}
      <button type="button" onClick={onClose} style={{ marginLeft: "auto" }}>Wróć do listy</button>
    </div>
    <div style={{ border: "2px solid #2563eb", borderRadius: 10, padding: "14px 16px", marginBottom: 14 }}>
      <h2 style={{ margin: "0 0 8px", color: "#0c2f4a" }}>{itemName}</h2>
      {details}
    </div>

    <section aria-label="Alternatywy w tej kategorii" style={{ border: "1px solid #e2e8f0", borderRadius: 10, padding: "12px 16px", marginBottom: 14, background: "#f8fafc" }}>
      <h3 style={{ margin: "0 0 4px" }}>Inne narzędzia z kategorii{peers?.category ? <>: <em>{peers.category}</em></> : ""}</h3>
      <p style={{ margin: "0 0 10px", color: "#64748b", fontSize: ".85rem" }}>
        Ocena ma sens w zestawieniu z tym, czego już używasz i co jeszcze czeka na radarze. Kategorie różnie zapisane w katalogach (np. „DecisionModels” i „decision-models”) są traktowane jako ta sama.
      </p>
      {peersError && <p className="errorText" role="alert">{peersError}</p>}
      {!peers && !peersError && <p style={{ color: "#64748b" }}>Ładowanie alternatyw…</p>}
      {peers && !peers.category && <p style={{ color: "#64748b" }}>To narzędzie nie ma kategorii, więc nie ma z czym go zestawić.</p>}
      {peers && peers.category && !radar.length && !peers.tools.length && <p style={{ color: "#64748b" }}>Brak innych narzędzi w tej kategorii — to jedyne w tym obszarze.</p>}
      {radar.map(peer => <div key={`r${peer.id}`} style={{ borderTop: "1px solid #e2e8f0", padding: "8px 0" }}>
        <strong>{peer.name}</strong><span style={badgeStyle(peer.status === "adopted")}>{statusLabel[peer.status]}</span>
        <button type="button" onClick={() => onOpenPeer(peer.id)} style={{ marginLeft: 8 }} title={`Otwórz kartę ${peer.name} do pełnej oceny`}>Oceń</button>
        {peer.status !== "adopted" && <span style={{ marginLeft: 8, display: "inline-flex", gap: 4, flexWrap: "wrap" }}>
          {actions.filter(([value]) => value !== peer.status && value !== "adopted").map(([value, label, help]) =>
            <button key={value} type="button" disabled={peerBusy === peer.id} title={`${peer.name}: ${help}`}
              aria-label={`${peer.name}: ${label}`} onClick={() => void movePeer(peer.id, value)}>{label}</button>)}
        </span>}
        {peer.homepage_url && <> · <a href={peer.homepage_url} target="_blank" rel="noreferrer">strona</a></>}
        {peer.github && <span style={{ color: "#475569", fontSize: ".85rem" }}> · ★ {peer.github.stars ?? "—"}{peer.github.pushed_at ? ` · push ${peer.github.pushed_at.slice(0, 10)}` : ""}{peer.github.archived ? " · zarchiwizowane" : ""}</span>}
        {peer.description && <div style={{ color: "#475569", fontSize: ".9rem", marginTop: 2 }}>{peer.description}</div>}
        {peer.personal_note && <div style={{ color: "#166534", fontSize: ".85rem", marginTop: 2 }}>Notatka: {peer.personal_note}</div>}
      </div>)}
      {peers?.tools.map(tool => <div key={`t${tool.id}`} style={{ borderTop: "1px solid #e2e8f0", padding: "8px 0" }}>
        <strong>{tool.name}</strong><span style={badgeStyle(true)}>W Spisie narzędzi</span>
        {tool.homepage_url && <> · <a href={tool.homepage_url} target="_blank" rel="noreferrer">strona</a></>}
        {(tool.license || tool.pricing) && <span style={{ color: "#475569", fontSize: ".85rem" }}> · {[tool.license, tool.pricing].filter(Boolean).join(" · ")}</span>}
        {tool.personal_notes && <div style={{ color: "#166534", fontSize: ".85rem", marginTop: 2 }}>Notatka: {tool.personal_notes}</div>}
      </div>)}
    </section>

    <label style={{ display: "block", marginBottom: 12 }}>
      <span>Notatka do decyzji (opcjonalnie)</span>
      <textarea value={note} onChange={event => setNote(event.target.value)} rows={3}
        placeholder="Dlaczego tak: czym wygrywa lub przegrywa z używanym narzędziem…"
        style={{ width: "100%", display: "block", marginTop: 4 }} />
    </label>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {actions.map(([value, label, help]) => <button key={value} title={help} aria-label={`${label}: ${help}`} disabled={busy}
        onClick={() => onDecide(value, noteChanged ? trimmedNote : null)}>{label}</button>)}
      {position > 0 && <button type="button" onClick={onNext} disabled={position >= total || busy} title="Zostaw bez zmian i przejdź do następnego narzędzia (notatka nie zostanie zapisana)">Pomiń</button>}
    </div>
  </div>;
}
