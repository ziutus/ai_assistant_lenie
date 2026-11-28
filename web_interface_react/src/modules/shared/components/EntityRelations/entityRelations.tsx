import React from "react";
import axios from "axios";
import ManualRelation from "./manualRelation";
import { type ApiProps, type Endpoint, type Relation, type Vocabulary, errorText, safeUrl } from "./types";

const EntityLink = ({ entity }: { entity: Endpoint }) => entity.type === "country" ? <span>{entity.name}</span>
  : <a href={`/${entity.type === "person" ? "persons" : "organizations"}/${entity.id}`}>{entity.name}</a>;
const claims: Record<string, string> = { zarzut_instytucji: "zarzut instytucji", anonimowe_zrodlo: "anonimowe źródło", deklaracja_strony: "deklaracja strony", zaprzeczenie: "zaprzeczenie" };
function RelationRow({ row, perspective, forwardLabel, busy, mutate }: { row: Relation; perspective: boolean; forwardLabel?: string; busy: boolean; mutate: (row: Relation, body?: object) => Promise<boolean> }) {
  const [editing, setEditing] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [title, setTitle] = React.useState(row.title ?? "");
  const [from, setFrom] = React.useState(row.valid_from ?? "");
  const [to, setTo] = React.useState(row.valid_to ?? "");
  const first = perspective && row.direction === "incoming" ? row.object : row.subject;
  const second = perspective ? row.other : row.object;
  return <li style={{ borderBottom: "1px solid #cbd5e1", padding: "8px 0", overflowWrap: "anywhere" }}>
    <EntityLink entity={first} /> — <strong>{perspective || row.direction === "outgoing" ? row.label : forwardLabel ?? row.relation}</strong>{row.title && `: ${row.title}`} — <EntityLink entity={second} />
    <div>{row.valid_from || row.valid_to ? `${row.valid_from ?? "…"} – ${row.valid_to ?? "…"}` : "Bez określonego okresu"} · {({ llm: "Model", wikidata: "Wikidata", manual: "Ręcznie" })[row.detection_method ?? ""]}</div>
    {row.evidence.map(e => <blockquote key={e.id} style={{ margin: "4px 0 4px 12px" }}>
      {e.claim && e.claim !== "fakt" && <strong style={{ padding: "2px 5px", background: e.claim === "zaprzeczenie" ? "#fee2e2" : "#fef3c7", color: e.claim === "zaprzeczenie" ? "#991b1b" : "#78350f", border: e.claim === "zaprzeczenie" ? "2px solid #b91c1c" : undefined }}>{claims[e.claim] ?? e.claim}</strong>}
      <div>{e.quote}</div>
      {e.document_id ? <a href={`/read/${e.document_id}`}>{e.document_title ?? "Dokument źródłowy"}</a> : safeUrl(e.source_url) && <a href={safeUrl(e.source_url)} target="_blank" rel="noreferrer">Źródło ↗</a>}
    </blockquote>)}
    {!row.editable ? <small>z danych organizacji/osoby</small> : <fieldset disabled={busy} style={{ border: 0, padding: 0 }}>
      {row.status !== "confirmed" && <button type="button" onClick={() => void mutate(row, { status: "confirmed" })}>Zatwierdź</button>}{" "}
      {row.status !== "rejected" && <button type="button" onClick={() => void mutate(row, { status: "rejected" })}>Odrzuć</button>}{" "}
      <button type="button" onClick={() => { setEditing(!editing); setTitle(row.title ?? ""); setFrom(row.valid_from ?? ""); setTo(row.valid_to ?? ""); }}>Edytuj</button>{" "}
      {deleting ? <><span>Usunąć to powiązanie? </span><button type="button" onClick={() => void mutate(row)}>Potwierdź usunięcie</button><button type="button" onClick={() => setDeleting(false)}>Anuluj usunięcie</button></>
        : <button type="button" onClick={() => setDeleting(true)}>Usuń</button>}
      {editing && <form onSubmit={async e => { e.preventDefault(); if (await mutate(row, { title: title.trim() || null, valid_from: from || null, valid_to: to || null })) setEditing(false); }}>
        <label>Tytuł <input maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
        <label>Od <input type="date" value={from} onChange={e => setFrom(e.target.value)} /></label>
        <label>Do <input type="date" min={from || undefined} value={to} onChange={e => setTo(e.target.value)} /></label>
        <button>Zapisz</button><button type="button" onClick={() => setEditing(false)}>Anuluj edycję</button>
      </form>}
    </fieldset>}
  </li>;
}
export default function EntityRelations({ apiUrl, apiKey, path, entity, revision = 0, onChange }: ApiProps & { path: string; entity?: Endpoint; revision?: number; onChange?: () => void }) {
  const headers = React.useMemo(() => ({ "x-api-key": apiKey }), [apiKey]);
  const [vocabulary, setVocabulary] = React.useState<Vocabulary[]>([]);
  React.useEffect(() => { let active = true; axios.get(`${apiUrl}/entity_relations/vocabulary`, { headers }).then(r => { if (active) setVocabulary(r.data.vocabulary ?? []); }).catch(() => undefined); return () => { active = false; }; }, [apiUrl, headers]);
  const [rows, setRows] = React.useState<Relation[]>([]);
  const [rejected, setRejected] = React.useState(false);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [reload, setReload] = React.useState(0);
  React.useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    axios.get(`${apiUrl}${path}`, { headers, params: rejected ? { include_rejected: 1 } : {} }).then(r => { if (active) setRows(r.data.relations ?? []); })
      .catch(e => { if (active) setError(errorText(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [apiUrl, headers, path, rejected, reload, revision]);
  const changed = () => { setReload(n => n + 1); onChange?.(); };
  const mutate = async (row: Relation, body?: object) => {
    if (!row.editable || busy) return false;
    setBusy(true); setError("");
    try {
      if (body) await axios.patch(`${apiUrl}/entity_relations/${row.id}`, body, { headers });
      else await axios.delete(`${apiUrl}/entity_relations/${row.id}`, { headers });
      changed();
      return true;
    } catch (e) { setError(errorText(e)); return false; } finally { setBusy(false); }
  };
  return <div>
    <label><input type="checkbox" checked={rejected} disabled={busy} onChange={e => setRejected(e.target.checked)} /> Pokaż odrzucone</label>
    {loading && <p role="status">Ładowanie powiązań…</p>}
    {error && <p role="alert">{error} <button onClick={() => setReload(n => n + 1)}>Spróbuj ponownie</button></p>}
    {!loading && !error && !rows.length && <p>Brak powiązań.</p>}
    {!loading && (["proposed", "confirmed", ...(rejected ? ["rejected"] : [])] as const).map(status => {
      const group = rows.filter(r => r.status === status);
      return group.length ? <section key={status}><h4>{({ proposed: "Propozycje", confirmed: "Potwierdzone", rejected: "Odrzucone" })[status]}</h4><ul style={{ listStyle: "none", padding: 0 }}>{group.map(row => <RelationRow key={`${row.source}:${row.id}`} row={row} perspective={!!entity} forwardLabel={vocabulary.find(v => v.value === row.relation)?.label} busy={busy} mutate={mutate} />)}</ul></section> : null;
    })}
    {entity && <ManualRelation apiUrl={apiUrl} apiKey={apiKey} entity={entity} onAdded={changed} disabled={busy} />}
  </div>;
}
