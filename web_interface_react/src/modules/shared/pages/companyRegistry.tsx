import React from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import CompanyRegistryResult, { type Result } from "../components/CompanyRegistryResult";
import type { IdentifierInput } from "../components/OrganizationIdentifiers";
import RequestErrorDetails from "../components/RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../utils/requestError";
import { probeBackend } from "../utils/backendProbe";

type Organization = { id: number; canonical_name: string; organization_type?: string; identifiers?: IdentifierInput[] };
type Match = {
  identifiers: IdentifierInput[]; disagreeing: string[]; owners: Organization[]; name_candidates: Organization[];
  registry_name: string; suggested_name: string; sole_proprietor: boolean;
};
type Check = Result & { lenie_match: Match };
type Saved = { organization: Organization; created: boolean; identifiers: IdentifierInput[]; warnings: string[] };

export default function CompanyRegistry() {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [params, setParams] = useSearchParams();
  const query = params.toString();
  const [kind, setKind] = React.useState(params.has("krs") ? "krs" : "nip");
  const [number, setNumber] = React.useState(params.get("nip") || params.get("krs") || "");
  const [result, setResult] = React.useState<Check | null>(null);
  const [checkedQuery, setCheckedQuery] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const [saved, setSaved] = React.useState<Saved | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [name, setName] = React.useState("");
  const [confirmed, setConfirmed] = React.useState(false);
  const lastQuery = React.useRef("");
  const generation = React.useRef(0);
  const headers = { "Content-Type": "application/x-www-form-urlencoded", "x-api-key": `${apiKey}` };

  async function report(cause: unknown, operation: string, startedAt: number, current: number,
    context: Record<string, string> = {}) {
    const info = describeRequestError(cause, operation, { startedAt, context });
    console.error(info.summary, info.details);
    if (current === generation.current) setError(info);
    if (!axios.isAxiosError(cause) || !cause.response) {
      const lines = await probeBackend(apiUrl);
      if (current === generation.current) setError({ ...info, details: [info.details, ...lines].join("\n") });
    }
  }

  async function check(input: Record<string, string>) {
    const current = ++generation.current;
    setBusy(true); setError(null); setResult(null); setSaved(null); setCreating(false); setConfirmed(false);
    const startedAt = Date.now();
    try {
      const response = await axios.get<Check>(`${apiUrl}/company_registry/check`, {
        headers, params: { ...input, match: "1" }, timeout: 180000,
      });
      if (current === generation.current) {
        setResult(response.data); setCheckedQuery(input); setName(response.data.lenie_match.suggested_name);
      }
    } catch (cause) { await report(cause, "Nie udało się sprawdzić rejestrów", startedAt, current); }
    finally { if (current === generation.current) setBusy(false); }
  }

  React.useEffect(() => {
    const key = `${apiUrl}|${query}`;
    if (lastQuery.current === key) return;
    lastQuery.current = key;
    const search = new URLSearchParams(query);
    const input: Record<string, string> = {};
    for (const type of ["nip", "krs"]) if (search.has(type)) input[type] = search.get(type)!;
    if (Object.keys(input).length) {
      setKind(input.nip !== undefined ? "nip" : "krs"); setNumber(input.nip ?? input.krs);
      void check(input);
    } else {
      ++generation.current; setResult(null); setSaved(null); setError(null); setBusy(false);
    }
    // URL navigation drives the lookup; the ref also avoids StrictMode's duplicate effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, apiUrl]);

  async function save(organizationId?: number) {
    const current = generation.current;
    const startedAt = Date.now();
    setBusy(true); setError(null);
    const payload = {
      ...checkedQuery, ...(organizationId ? { organization_id: organizationId } : { canonical_name: name }),
      confirm_sole_proprietor: confirmed,
    };
    try {
      const response = await axios.post<Saved>(`${apiUrl}/company_registry/organizations`, payload,
        { headers: { ...headers, "Content-Type": "application/json" }, timeout: 180000 });
      if (current === generation.current) setSaved(response.data);
    } catch (cause) {
      await report(cause, "Nie udało się zapisać organizacji", startedAt, current, {
        "Rozmiar zapisywanych danych": `${new Blob([JSON.stringify(payload)]).size} B`,
      });
    }
    finally { if (current === generation.current) setBusy(false); }
  }

  const match = result?.lenie_match;
  const canSave = !busy && (!match?.sole_proprietor || confirmed);
  return <section aria-label="Rejestr firm">
    <h1>Rejestr firm</h1>
    <form onSubmit={event => {
      event.preventDefault();
      const input = { [kind]: number.trim() };
      if (new URLSearchParams(input).toString() === query) void check(input);
      else setParams(input);
    }}>
      <label>Rodzaj identyfikatora <select value={kind} disabled={busy} onChange={e => setKind(e.target.value)}>
        <option value="nip">NIP</option><option value="krs">KRS</option>
      </select></label>{" "}
      <label>Numer <input value={number} disabled={busy} onChange={e => setNumber(e.target.value)} /></label>{" "}
      <button disabled={busy || !number.trim()}>{busy ? "Proszę czekać…" : "Sprawdź"}</button>
    </form>
    {error && <div role="alert"><p>{error.summary}</p><RequestErrorDetails details={error.details} /></div>}
    {saved && <section role="status"><p>Zapisano organizację: <Link to={`/organizations/${saved.organization.id}`}>
      {saved.organization.canonical_name}</Link></p>{saved.warnings.map((warning, i) => <p key={i}>{warning}</p>)}</section>}
    {match && <section aria-label="W Lenie">
      <h2>W Lenie</h2>
      {!saved && (match.owners.length ? match.owners.map(owner => <p key={owner.id}>
        Ten numer ma już organizacja <Link to={`/organizations/${owner.id}`}>{owner.canonical_name}</Link>
      </p>) : <>
        {match.sole_proprietor && <label><input type="checkbox" checked={confirmed} disabled={busy}
          onChange={e => setConfirmed(e.target.checked)} />Potwierdzam zapis jednoosobowej działalności;
          jej nazwa zwykle zawiera imię i nazwisko właściciela.</label>}
        {match.name_candidates.map(candidate => <div key={candidate.id}>
          <Link to={`/organizations/${candidate.id}`}>{candidate.canonical_name}</Link>
          {candidate.organization_type && <span> ({candidate.organization_type})</span>}
          <p>{candidate.identifiers?.map(n => `${n.identifier_type.toUpperCase()} ${n.value}`).join(", ")}</p>
          <button disabled={!canSave} onClick={() => void save(candidate.id)}>Przypisz numery do tej organizacji</button>
        </div>)}
        {!creating && <button disabled={busy || !match.registry_name} onClick={() => setCreating(true)}>
          {match.name_candidates.length ? "To inna firma, utwórz nową" : "Dodaj organizację"}</button>}
        {creating && <form onSubmit={event => { event.preventDefault(); void save(); }}>
          <label>Nazwa organizacji <input value={name} maxLength={200} required disabled={busy}
            onChange={e => setName(e.target.value)} /></label>
          <p>Numery do zapisania: {match.identifiers.map(n => `${n.identifier_type.toUpperCase()} ${n.value}`).join(", ") || "brak"}</p>
          <p>Pełna nazwa jako alias: {match.registry_name}</p>
          <button disabled={!canSave || !name.trim()}>Zapisz organizację</button>
        </form>}
      </>)}
      {match.disagreeing.length > 0 && <p role="status">Rozbieżne numery: {match.disagreeing.join(", ")}. Nie zostaną zapisane.</p>}
      {!match.registry_name && <p>Żaden rejestr nie potwierdził firmy.</p>}
    </section>}
    {result && <CompanyRegistryResult result={result} />}
  </section>;
}
