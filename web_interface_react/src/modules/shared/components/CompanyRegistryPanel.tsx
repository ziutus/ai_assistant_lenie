import React from "react";
import axios from "axios";
import CollapsibleSection from "./CollapsibleSection/collapsibleSection";
import RequestErrorDetails from "./RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../utils/requestError";
import { probeBackend } from "../utils/backendProbe";

type Filing = {
  reference: string; is_current: boolean; presented_from: string; presented_to: string;
  beneficiaries: { name: string; group_name: string; ownership: { kind: string; text: string }[] }[];
};
type Shareholder = { name: string; shares: string; added_at: string | null; removed_at: string | null };
type Result = {
  warnings: { code: string; message: string }[];
  crbr: { status: string; message: string; filings: Filing[] };
  krs: { status: string; message: string; name?: string; state_as_of?: string;
    current_shareholders?: Shareholder[]; former_shareholders?: Shareholder[] };
};

function Filings({ filings }: { filings: Filing[] }) {
  return <>{filings.map((filing, i) => <div key={`${filing.reference}-${i}`}>
    <p>Zgłoszenie: {filing.presented_from} – {filing.presented_to}</p>
    <ul>{filing.beneficiaries.map((person, j) => <li key={j}>
      <strong>{person.name || person.group_name}</strong>
      <ul>{person.ownership.map((basis, k) => <li key={k}>
        {({ direct: "Bezpośrednie", indirect: "Pośrednie", other: "Inne" }[basis.kind] || "Uprawnienia")}: {basis.text}
      </li>)}</ul>
    </li>)}</ul>
  </div>)}</>;
}

export default function CompanyRegistryPanel({ apiUrl, headers }: { apiUrl: string; headers: Record<string, string> }) {
  const [kind, setKind] = React.useState("nip");
  const [identifier, setIdentifier] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<Result | null>(null);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);

  async function check(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null); setResult(null);
    const startedAt = Date.now();
    try {
      const response = await axios.get<Result>(`${apiUrl}/company_registry/check`, {
        headers, params: { [kind]: identifier }, timeout: 180000,
      });
      setResult(response.data);
    } catch (cause) {
      const info = describeRequestError(cause, "Nie udało się sprawdzić rejestrów", { startedAt });
      console.error(info.summary, info.details);
      setError(info);
      if (!axios.isAxiosError(cause) || !cause.response) {
        const lines = await probeBackend(apiUrl);
        setError({ ...info, details: [info.details, ...lines].join("\n") });
      }
    } finally { setBusy(false); }
  }

  return <CollapsibleSection title="Rejestry: CRBR i KRS">
    <form onSubmit={check} style={{ marginTop: 12 }}>
      <label>Rodzaj identyfikatora <select value={kind} disabled={busy} onChange={e => setKind(e.target.value)}>
        <option value="nip">NIP</option><option value="krs">KRS</option>
      </select></label>{" "}
      <label>Identyfikator <input value={identifier} disabled={busy} onChange={e => setIdentifier(e.target.value)} /></label>{" "}
      <button disabled={busy || !identifier.trim()}>{busy ? "Sprawdzanie…" : "Sprawdź"}</button>
    </form>
    {error && <div role="alert"><p>{error.summary}</p><RequestErrorDetails details={error.details} /></div>}
    {result && <div aria-live="polite">
      {result.warnings.length > 0 && <div role="status"><h4>Wskazówki do weryfikacji</h4>
        <ul>{result.warnings.map(w => <li key={w.code}>{w.message}</li>)}</ul></div>}
      <h4>Aktualni beneficjenci CRBR</h4><p>{result.crbr.message}</p>
      <Filings filings={result.crbr.filings.filter(f => f.is_current)} />
      <h4>Wspólnicy KRS {result.krs.name}</h4><p>{result.krs.message}</p>
      {result.krs.state_as_of && <p>Stan na: {result.krs.state_as_of}</p>}
      {([['Aktualni wspólnicy', result.krs.current_shareholders], ['Byli wspólnicy', result.krs.former_shareholders]] as const)
        .map(([title, rows]) => rows && <div key={title}><h5>{title}</h5>
          {rows.length === 0 ? <p>Brak wpisów.</p> : <ul>{rows.map((row, i) => <li key={i}>
            {row.name}: {row.shares}{row.added_at && `; wpis: ${row.added_at}`}
            {row.removed_at && `; wykreślenie: ${row.removed_at}`}
          </li>)}</ul>}</div>)}
      {result.crbr.filings.some(f => !f.is_current) && <CollapsibleSection title="Starsze zgłoszenia CRBR">
        <Filings filings={result.crbr.filings.filter(f => !f.is_current)} />
      </CollapsibleSection>}
    </div>}
  </CollapsibleSection>;
}
