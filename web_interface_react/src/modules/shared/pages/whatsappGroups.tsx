import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

export interface WhatsappGroupInfo {
  id: number;
  jid: string;
  name: string;
  is_community: boolean;
  parent_id: number | null;
  is_announce: boolean;
  is_default_sub: boolean;
  participant_count: number;
  active_members: number;
  in_contacts: number;
  missing: number;
  unverified: number;
  joins_7d: number;
  leaves_7d: number;
  last_synced_at: string | null;
  conversation_id: number | null;
}

export const formatGroupDate = (value: string | null) => value ? new Date(value).toLocaleString("pl-PL") : "—";
export const groupTableStyle: React.CSSProperties = {
  width: "100%", minWidth: 1050, tableLayout: "fixed", borderSpacing: "12px 16px", textAlign: "left", overflowWrap: "anywhere",
};

export default function WhatsappGroups() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [data, setData] = React.useState<{ groups: WhatsappGroupInfo[]; summary: { groups: number; communities: number } } | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [revision, setRevision] = React.useState(0);

  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    axios.get(`${apiUrl}/whatsapp_groups`, { headers: { "x-api-key": apiKey }, signal: controller.signal })
      .then(({ data: next }) => { if (!controller.signal.aborted) setData(next); })
      .catch(() => { if (!controller.signal.aborted) { setError("Nie udało się pobrać grup."); setData(null); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [apiUrl, apiKey, revision]);

  const sync = async () => {
    setBusy(true); setError(""); setMessage("");
    try {
      await axios.post(`${apiUrl}/whatsapp_groups/sync`, {}, { headers: { "x-api-key": apiKey } });
      setMessage("Odczyt został zlecony. Wykona go worker w tle, więc odświeżenie listy potrwa chwilę. Za chwilę wybierz „Odśwież listę”.");
    } catch { setError("Nie udało się zlecić odczytu. Spróbuj ponownie."); }
    finally { setBusy(false); }
  };

  const groups = data?.groups ?? [];
  const communities = groups.filter((g) => g.is_community);
  const communityIds = new Set(communities.map((g) => g.id));
  const rows = communities.flatMap((g) => [{ group: g, nested: false },
    ...groups.filter((child) => !child.is_community && child.parent_id === g.id).map((group) => ({ group, nested: true }))]);
  rows.push(...groups.filter((g) => !g.is_community && (g.parent_id === null || !communityIds.has(g.parent_id)))
    .map((group) => ({ group, nested: false })));

  return <section style={{ lineHeight: 1.7 }}>
    <h2>Grupy WhatsApp</h2>
    <p>Lista pochodzi z odczytu co ok. 30 minut. Zmiany składu są wykrywane między odczytami.</p>
    <div style={{ display: "flex", gap: 16, margin: "16px 0", flexWrap: "wrap" }}>
      <button type="button" className="button" disabled={busy} onClick={() => void sync()}>{busy ? "Zlecam odczyt…" : "Odczytaj teraz"}</button>
      <button type="button" className="button" disabled={loading || busy} onClick={() => setRevision((v) => v + 1)}>Odśwież listę</button>
    </div>
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
    {loading && <p role="status">Ładowanie grup…</p>}
    {!loading && data && <>
      <p>Grupy: {data.summary.groups} · Społeczności: {data.summary.communities}</p>
      <div style={{ overflowX: "auto" }}><table style={groupTableStyle}>
        <thead><tr><th style={{ width: "22%" }}>Nazwa</th><th>Osób</th><th>W kontaktach</th><th>Brak w kontaktach</th><th>Do weryfikacji</th><th>Dołączyło (7 dni)</th><th>Odeszło (7 dni)</th><th>Ostatni odczyt</th></tr></thead>
        <tbody>{rows.map(({ group: g, nested }) => <tr key={g.id}>
          <td style={{ paddingLeft: nested ? 28 : 0 }}><NavLink to={`/whatsapp-groups/${g.id}`}>{g.name || g.jid}</NavLink>
            {g.is_community && <div>Społeczność</div>}{g.is_announce && <div>Ogłoszenia</div>}</td>
          <td>{g.participant_count}</td><td>{g.in_contacts}</td><td>{g.missing}</td><td>{g.unverified}</td>
          <td>{g.joins_7d}</td><td>{g.leaves_7d}</td><td>{formatGroupDate(g.last_synced_at)}</td>
        </tr>)}</tbody>
      </table></div>
      {!groups.length && <p>Brak odczytanych grup. Wybierz „Odczytaj teraz”.</p>}
    </>}
  </section>;
}
