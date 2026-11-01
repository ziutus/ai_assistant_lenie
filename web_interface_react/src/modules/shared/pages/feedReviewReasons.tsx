import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";
import RequestErrorDetails from "../components/RequestErrorDetails/requestErrorDetails";
import type { RequestErrorInfo } from "../utils/requestError";
import { reasonsRequest, type FeedReviewReason } from "../services/feedReviewReasons";

export default function FeedReviewReasons() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [rows, setRows] = React.useState<FeedReviewReason[]>([]);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [code, setCode] = React.useState("");
  const [label, setLabel] = React.useState("");
  const [order, setOrder] = React.useState(100);
  const [editing, setEditing] = React.useState<FeedReviewReason | null>(null);
  const [pending, setPending] = React.useState<string | null>(null);
  const load = React.useCallback(async () => {
    const data = await reasonsRequest(`${apiUrl}/feed_review_reasons`, apiKey || "");
    setRows(data.reasons || []);
  }, [apiUrl, apiKey]);
  React.useEffect(() => {
    void load().catch(setError).finally(() => setLoaded(true));
  }, [load]);
  const write = async (method: string, target = "", body?: object) => {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      await reasonsRequest(`${apiUrl}/feed_review_reasons${target ? `/${encodeURIComponent(target)}` : ""}`, apiKey || "", method, body);
      setEditing(null); setPending(null);
      if (method === "POST") { setCode(""); setLabel(""); setOrder(100); }
      await load();
    } catch (cause) { setError(cause as RequestErrorInfo); }
    finally { setBusy(false); }
  };
  return <section>
    <h1>Powody pominięcia</h1>
    {error && <div role="alert"><p>{error.summary}</p><RequestErrorDetails details={error.details} /></div>}
    <form onSubmit={event => { event.preventDefault(); void write("POST", "", { code, label, sort_order: order }); }}>
      <label>Kod <input aria-label="Kod nowego powodu" required pattern="[a-z][a-z0-9_]{1,39}" maxLength={40} value={code} onChange={event => setCode(event.target.value)} /></label>{" "}
      <label>Etykieta <input aria-label="Etykieta nowego powodu" required maxLength={120} value={label} onChange={event => setLabel(event.target.value)} /></label>{" "}
      <label>Kolejność <input aria-label="Kolejność nowego powodu" type="number" min={0} max={10000} required value={order} onChange={event => setOrder(Number(event.target.value))} /></label>{" "}
      <button disabled={busy || !label.trim()}>Dodaj powód</button>
    </form>
    {!loaded && <p>Ładowanie…</p>}
    {loaded && rows.length === 0 && <p>Brak powodów pominięcia.</p>}
    <table><thead><tr>{["Kod", "Etykieta", "Kolejność", "Wybieralny", "Aktywny", "Użyć", "Akcje"].map(text => <th key={text}>{text}</th>)}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.code}>
        <td>{row.code}{row.system && <span> (systemowy)</span>}</td>
        <td>{editing?.code === row.code ? <input aria-label={`Etykieta ${row.code}`} maxLength={120} value={editing.label} onChange={event => setEditing({ ...editing, label: event.target.value })} /> : row.label}</td>
        <td>{editing?.code === row.code ? <input aria-label={`Kolejność ${row.code}`} type="number" min={0} max={10000} value={editing.sort_order} onChange={event => setEditing({ ...editing, sort_order: Number(event.target.value) })} /> : row.sort_order}</td>
        <td><input type="checkbox" aria-label={`Wybieralny ${row.code}`} checked={row.selectable} disabled={busy || row.system} onChange={event => void write("PATCH", row.code, { selectable: event.target.checked })} /></td>
        <td><input type="checkbox" aria-label={`Aktywny ${row.code}`} checked={row.active} disabled={busy || row.system} onChange={event => void write("PATCH", row.code, { active: event.target.checked })} /></td>
        <td>{row.usage_count}</td>
        <td>{editing?.code === row.code ? <>
          <button disabled={busy || !editing.label.trim()} onClick={() => void write("PATCH", row.code, { label: editing.label, sort_order: editing.sort_order })}>Zapisz</button>{" "}
          <button disabled={busy} onClick={() => setEditing(null)}>Anuluj edycję</button>
        </> : <button disabled={busy} onClick={() => setEditing({ ...row })}>Edytuj</button>}{" "}
          {!row.system && (pending === row.code ? <>
            <span>Usunąć „{row.label}”?</span>{" "}
            <button disabled={busy} onClick={() => void write("DELETE", row.code)}>Potwierdź usunięcie</button>{" "}
            <button disabled={busy} onClick={() => setPending(null)}>Anuluj usunięcie</button>
          </> : <button disabled={busy || row.usage_count > 0} title={row.usage_count > 0 ? "Powód jest używany — dezaktywuj go zamiast usuwać" : undefined} onClick={() => setPending(row.code)}>Usuń</button>)}
        </td>
      </tr>)}</tbody>
    </table>
  </section>;
}
