import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import RequestErrorDetails from "./RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../utils/requestError";
import { probeBackend } from "../utils/backendProbe";

type Organization = { id: number; canonical_name: string };
type Relation = {
  id: number; organization_id: number; subject_name: string; subject_krs: string | null;
  organization: Organization | null; holding_organization?: Organization;
  name_candidates: Organization[]; details: string | null; valid_from: string | null; valid_to: string | null;
  source: string; source_url: string | null; checked_at: string | null;
};
type Relations = { shareholders: Relation[]; holdings: Relation[] };

export default function RelatedCompanies({ organizationId, apiUrl, headers, refreshKey = 0 }: {
  organizationId: number; apiUrl: string; headers: Record<string, string>; refreshKey?: number;
}) {
  const [data, setData] = React.useState<Relations>({ shareholders: [], holdings: [] });
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const [busy, setBusy] = React.useState(false);
  const headerKey = JSON.stringify(headers);
  const stableHeaders = React.useMemo(() => JSON.parse(headerKey) as Record<string, string>, [headerKey]);
  const endpoint = `${apiUrl}/organizations/${organizationId}`;
  const report = React.useCallback(async (cause: unknown, startedAt: number) => {
    const info = describeRequestError(cause, "Nie udało się odczytać lub zapisać powiązań firm",
      { startedAt, context: { Organizacja: organizationId } });
    console.error(cause);
    setError(info);
    if (!axios.isAxiosError(cause) || !cause.response) {
      const lines = await probeBackend(apiUrl);
      setError({ ...info, details: [info.details, ...lines].join("\n") });
    }
  }, [apiUrl, organizationId]);

  React.useEffect(() => {
    let active = true;
    const startedAt = Date.now();
    setData({ shareholders: [], holdings: [] }); setError(null);
    void axios.get<Relations>(`${endpoint}/related_companies`, { headers: stableHeaders }).then(response => {
      if (active) setData({ shareholders: response.data.shareholders || [], holdings: response.data.holdings || [] });
    }).catch(cause => { if (active) void report(cause, startedAt); });
    return () => { active = false; };
  }, [endpoint, stableHeaders, refreshKey, report]);

  async function link(rowId: number, target: number | null) {
    const startedAt = Date.now(); setBusy(true); setError(null);
    try {
      const response = await axios.patch<Relations>(`${endpoint}/relations/${rowId}`,
        { related_organization_id: target }, { headers: { ...stableHeaders, "Content-Type": "application/json" } });
      setData(response.data);
    } catch (cause) { await report(cause, startedAt); }
    finally { setBusy(false); }
  }

  if (!data.shareholders.length && !data.holdings.length && !error) return null;
  return <section>
    <h3>Powiązane firmy</h3>
    {error && <div role="alert"><p>{error.summary}</p><RequestErrorDetails details={error.details} /></div>}
    {([['Wspólnicy', data.shareholders], ['Udziały w innych firmach', data.holdings]] as const).map(([title, rows]) =>
      rows.length > 0 && <div key={title}><h4>{title}</h4><ul>{rows.map(row =>
        <CompanyRow key={row.id} row={row} busy={busy} link={link} apiUrl={apiUrl} headers={stableHeaders} report={report} />
      )}</ul></div>)}
  </section>;
}

function CompanyRow({ row, busy, link, apiUrl, headers, report }: {
  row: Relation; busy: boolean; link: (id: number, target: number | null) => Promise<void>;
  apiUrl: string; headers: Record<string, string>; report: (cause: unknown, startedAt: number) => Promise<void>;
}) {
  const [confirm, setConfirm] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<Organization[]>([]);
  const [selected, setSelected] = React.useState("");
  const [searching, setSearching] = React.useState(false);
  const shown = row.holding_organization || row.organization;
  async function search(event: React.FormEvent) {
    event.preventDefault();
    const startedAt = Date.now(); setSearching(true); setResults([]); setSelected("");
    try {
      const response = await axios.get(`${apiUrl}/organizations`, { params: { q: query }, headers });
      setResults((response.data.entries || []).filter((org: Organization) => org.id !== row.organization_id));
    } catch (cause) { await report(cause, startedAt); }
    finally { setSearching(false); }
  }
  return <li style={{ marginBottom: 12 }}>
    {shown ? <Link to={`/organizations/${shown.id}`}>{shown.canonical_name}</Link> : row.subject_name}
    {row.organization && !row.holding_organization && row.subject_name !== row.organization.canonical_name
      && <span> ({row.subject_name})</span>}
    {row.subject_krs && <span> · KRS {row.subject_krs}</span>}
    <span> · {row.valid_to ? `Były wspólnik — do ${row.valid_to}` : "Obecny wspólnik"}
      {row.valid_from && ` · od ${row.valid_from}`}</span>
    {row.details && <div>{row.details}</div>}
    <div>Źródło: {row.source_url ? <a href={row.source_url} target="_blank" rel="noreferrer">{row.source.toUpperCase()}</a>
      : row.source.toUpperCase()}{row.checked_at && ` · Sprawdzono: ${row.checked_at.replace("T", " ")}`}</div>
    {row.organization ? (confirm ? <>
      Odłączyć firmę? <button disabled={busy} onClick={() => void link(row.id, null)}>Potwierdź odłączenie</button>{" "}
      <button disabled={busy} onClick={() => setConfirm(false)}>Anuluj</button>
    </> : <button disabled={busy} onClick={() => setConfirm(true)}>Odłącz</button>) : <>
      {row.name_candidates.map(candidate => <div key={candidate.id}>{candidate.canonical_name}{" "}
        <button disabled={busy} onClick={() => void link(row.id, candidate.id)}>To ta firma</button></div>)}
      <form onSubmit={event => void search(event)}>
        <label>Szukaj organizacji <input value={query} onChange={event => setQuery(event.target.value)} /></label>{" "}
        <button disabled={busy || searching || !query.trim()}>Szukaj</button>
      </form>
      {results.length > 0 && <div><label>Wybierz firmę <select value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">Wybierz</option>{results.map(org => <option key={org.id} value={org.id}>{org.canonical_name}</option>)}
      </select></label>{" "}<button disabled={busy || !selected} onClick={() => void link(row.id, Number(selected))}>Powiąż</button></div>}
      {row.subject_krs && <Link to={`/company-registry?krs=${encodeURIComponent(row.subject_krs)}`}>Sprawdź w Rejestrze firm</Link>}
    </>}
  </li>;
}
