import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import CompanyRegistryPanel from "./CompanyRegistryPanel";
import RequestErrorDetails from "./RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../utils/requestError";
import { probeBackend } from "../utils/backendProbe";

export type IdentifierInput = {
  country_code: string; identifier_type: string; value: string; source_url?: string; note?: string;
};
type Identifier = IdentifierInput & { id: number };
type Conflict = { id: number; canonical_name: string };

export default function OrganizationIdentifiers({ organizationId, apiUrl, headers }: {
  organizationId: number; apiUrl: string; headers: Record<string, string>;
}) {
  const [rows, setRows] = React.useState<Identifier[]>([]);
  const [country, setCountry] = React.useState("PL");
  const [kind, setKind] = React.useState("nip");
  const [customKind, setCustomKind] = React.useState("");
  const [value, setValue] = React.useState("");
  const [sourceUrl, setSourceUrl] = React.useState("");
  const [note, setNote] = React.useState("");
  const [confirmId, setConfirmId] = React.useState<number | null>(null);
  const [adding, setAdding] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const [conflict, setConflict] = React.useState<Conflict | null>(null);
  const endpoint = `${apiUrl}/organizations/${organizationId}/identifiers`;
  const headerKey = JSON.stringify(headers);
  const stableHeaders = React.useMemo(() => JSON.parse(headerKey) as Record<string, string>, [headerKey]);

  const report = React.useCallback(async (cause: unknown, operation: string, startedAt: number) => {
    const info = describeRequestError(cause, operation, { startedAt, context: { Organizacja: organizationId } });
    console.error(info.summary, info.details);
    setError(info);
    if (axios.isAxiosError(cause) && cause.response?.status === 409) {
      setConflict(cause.response.data.conflict_organization || null);
    }
    if (!axios.isAxiosError(cause) || !cause.response) {
      const lines = await probeBackend(apiUrl);
      setError({ ...info, details: [info.details, ...lines].join("\n") });
    }
  }, [organizationId, apiUrl]);

  const refresh = React.useCallback(async () => {
    const response = await axios.get<{ identifiers: Identifier[] }>(endpoint, { headers: stableHeaders });
    setRows(response.data.identifiers || []);
  }, [endpoint, stableHeaders]);

  React.useEffect(() => {
    const startedAt = Date.now();
    void refresh().catch(cause => report(cause, "Nie udało się pobrać numerów rejestrowych", startedAt));
  }, [refresh, report]);

  async function add(input: IdentifierInput) {
    const startedAt = Date.now();
    setBusy(true); setError(null); setConflict(null);
    try {
      // The page sends form-encoded headers by default; this endpoint reads JSON.
      await axios.post(endpoint, input, { headers: { ...stableHeaders, "Content-Type": "application/json" } });
      await refresh();
      return true;
    } catch (cause) {
      await report(cause, "Nie udało się dodać numeru rejestrowego", startedAt);
      return false;
    } finally { setBusy(false); }
  }

  async function remove(rowId: number) {
    const startedAt = Date.now();
    setBusy(true); setError(null); setConflict(null);
    try {
      await axios.delete(`${endpoint}/${rowId}`, { headers: stableHeaders });
      setConfirmId(null);
      await refresh();
    } catch (cause) {
      await report(cause, "Nie udało się usunąć numeru rejestrowego", startedAt);
    } finally { setBusy(false); }
  }

  return <section>
    <h3>Numery rejestrowe</h3>
    {rows.length === 0 ? <p>Brak numerów rejestrowych.</p> : <ul>{rows.map(row => <li key={row.id}>
      {row.country_code} {row.identifier_type.toUpperCase()}: {row.value}{row.note && ` — ${row.note}`} {" "}
      {row.source_url && <a href={row.source_url} target="_blank" rel="noreferrer">Źródło</a>} {" "}
      {confirmId === row.id ? <>
        Usunąć numer? <button disabled={busy} onClick={() => void remove(row.id)}>Potwierdź usunięcie</button>{" "}
        <button disabled={busy} onClick={() => setConfirmId(null)}>Anuluj</button>
      </> : <button disabled={busy} onClick={() => setConfirmId(row.id)}>Usuń</button>}
    </li>)}</ul>}
    {!adding && <button type="button" onClick={() => setAdding(true)}>➕ Dodaj numer</button>}
    {adding && <form onSubmit={async event => {
      event.preventDefault();
      if (await add({ country_code: country, identifier_type: kind === "other" ? customKind : kind,
        value, source_url: sourceUrl, note })) { setValue(""); setSourceUrl(""); setNote(""); setAdding(false); }
    }}>
      <fieldset disabled={busy}>
        <label>Kraj <input value={country} maxLength={2} required onChange={e => setCountry(e.target.value)} /></label>{" "}
        <label>Typ numeru <select value={kind} onChange={e => setKind(e.target.value)}>
          <option value="nip">NIP</option><option value="krs">KRS</option><option value="regon">REGON</option>
          <option value="other">inny</option>
        </select></label>{" "}
        {kind === "other" && <label>Nazwa typu <input required pattern="[a-z0-9_]+" maxLength={30}
          value={customKind} onChange={e => setCustomKind(e.target.value)} /></label>}
        <label>Numer <input required value={value} onChange={e => setValue(e.target.value)} /></label>{" "}
        <label>Adres źródła (opcjonalnie) <input type="url" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} /></label>{" "}
        <label>Notatka (opcjonalnie) <input value={note} onChange={e => setNote(e.target.value)} /></label>{" "}
        <button>Zapisz numer</button>{" "}
        <button type="button" onClick={() => { setAdding(false); setError(null); setConflict(null); }}>Anuluj</button>
      </fieldset>
    </form>}
    {error && <div role="alert"><p>{error.summary}</p>
      {conflict && <Link to={`/organizations/${conflict.id}`}>{conflict.canonical_name}</Link>}
      <RequestErrorDetails details={error.details} /></div>}
    {rows.some(row => row.country_code === "PL" && ["nip", "krs"].includes(row.identifier_type))
      && <CompanyRegistryPanel apiUrl={apiUrl} headers={stableHeaders} organizationId={organizationId}
      identifiers={rows} onAddIdentifier={add} savingIdentifier={busy}
      onIdentifiersChanged={() => {
        const startedAt = Date.now();
        void refresh().catch(cause => report(cause, "Nie udało się pobrać numerów rejestrowych", startedAt));
      }} />}
  </section>;
}
