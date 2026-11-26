import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import CollapsibleSection from "./CollapsibleSection/collapsibleSection";
import RequestErrorDetails from "./RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../utils/requestError";
import { probeBackend } from "../utils/backendProbe";
import type { IdentifierInput } from "./OrganizationIdentifiers";

type Filing = {
  reference: string; is_current: boolean; presented_from: string; presented_to: string;
  beneficiaries: { name: string; group_name: string; ownership: { kind: string; text: string }[] }[];
};
type Shareholder = { name: string; shares: string; added_at: string | null; removed_at: string | null };
type Result = {
  vat?: { status: string; message: string; subject?: Record<string, string> };
  ceidg?: { status: string; message: string; company?: Record<string, string> };
  suggested_identifiers?: (IdentifierInput & {
    reason_message?: string; conflict_organization?: { id: number; canonical_name: string };
  })[];
  identifier_sync?: { added: IdentifierInput[] };
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

export default function CompanyRegistryPanel({ apiUrl, headers, organizationId,
  identifiers = [], onAddIdentifier, onIdentifiersChanged, savingIdentifier }: {
  apiUrl: string; headers: Record<string, string>; organizationId?: number;
  identifiers?: IdentifierInput[]; onAddIdentifier?: (input: IdentifierInput) => Promise<boolean>; savingIdentifier?: boolean;
  onIdentifiersChanged?: () => void;
}) {
  const [kind, setKind] = React.useState("nip");
  const [identifier, setIdentifier] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<Result | null>(null);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const [failedSuggestion, setFailedSuggestion] = React.useState<string | null>(null);

  async function check(useOrganization = false) {
    setBusy(true); setError(null); setResult(null); setFailedSuggestion(null);
    const startedAt = Date.now();
    try {
      // For the organization the server also stores the KRS / REGON that fit; a typed number only reads.
      const response = useOrganization
        ? await axios.post<Result>(`${apiUrl}/organizations/${organizationId}/identifiers/sync`, {},
          { headers, timeout: 180000 })
        : await axios.get<Result>(`${apiUrl}/company_registry/check`, {
          headers, params: { [kind]: identifier }, timeout: 180000,
        });
      setResult(response.data);
      if (response.data.identifier_sync?.added.length) onIdentifiersChanged?.();
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

  // An organization is checked by its own stored numbers; typing a number is for use outside one.
  const content = <>
    {organizationId ? <button disabled={busy || savingIdentifier} onClick={() => void check(true)}>
      {busy ? "Sprawdzanie…" : "🔎 Sprawdź w rejestrach (CRBR, KRS, VAT, CEIDG)"}</button>
    : <form onSubmit={event => { event.preventDefault(); void check(); }} style={{ marginTop: 12 }}>
      <label>Rodzaj identyfikatora <select value={kind} disabled={busy} onChange={e => setKind(e.target.value)}>
        <option value="nip">NIP</option><option value="krs">KRS</option>
      </select></label>{" "}
      <label>Identyfikator <input value={identifier} disabled={busy} onChange={e => setIdentifier(e.target.value)} /></label>{" "}
      <button disabled={busy || !identifier.trim()}>{busy ? "Sprawdzanie…" : "Sprawdź"}</button>
    </form>}
    {error && <div role="alert"><p>{error.summary}</p><RequestErrorDetails details={error.details} /></div>}
    {result && <div aria-live="polite">
      {result.warnings.length > 0 && <div role="status"><h4>Wskazówki do weryfikacji</h4>
        <ul>{result.warnings.map(w => <li key={w.code}>{w.message}</li>)}</ul></div>}
      {!!result.identifier_sync?.added.length && <p role="status">Dodano z rejestrów:{" "}
        {result.identifier_sync.added.map(row => `${row.identifier_type.toUpperCase()} ${row.value}`).join(", ")}.</p>}
      {([['VAT — biała lista', result.vat, result.vat?.subject], ['CEIDG', result.ceidg, result.ceidg?.company]] as const)
        .map(([title, section, fields]) => section && <section key={title}>
          <h4>{title}</h4><p>{section.message}</p>
          {fields && <dl>{Object.entries(fields).filter(([, value]) => value).map(([key, value]) =>
            <React.Fragment key={key}><dt>{({ name: "Nazwa", nip: "NIP", krs: "KRS", regon: "REGON",
              statusVat: "Status VAT", status: "Status", residenceAddress: "Adres zamieszkania", workingAddress: "Adres działalności",
              registrationLegalDate: "Data rejestracji", removalDate: "Data wykreślenia", start_date: "Data rozpoczęcia",
              suspension_date: "Data zawieszenia", removal_date: "Data wykreślenia", city: "Miasto", postal_code: "Kod pocztowy",
            } as Record<string, string>)[key] || key}</dt><dd>{value}</dd></React.Fragment>)}</dl>}
        </section>)}
      {onAddIdentifier && result.suggested_identifiers?.filter(suggestion => !identifiers.some(row =>
        row.country_code === suggestion.country_code && row.identifier_type === suggestion.identifier_type && row.value === suggestion.value))
        .map(suggestion => <p key={`${suggestion.identifier_type}:${suggestion.value}`}>
          {suggestion.identifier_type.toUpperCase()}: {suggestion.value}{" "}
          {suggestion.reason_message && <span>— {suggestion.reason_message}{" "}</span>}
          {suggestion.conflict_organization && <><Link to={`/organizations/${suggestion.conflict_organization.id}`}>
            {suggestion.conflict_organization.canonical_name}</Link>{" "}</>}
          <button disabled={savingIdentifier} onClick={async () => {
            const key = `${suggestion.identifier_type}:${suggestion.value}`;
            setFailedSuggestion(null);
            if (!await onAddIdentifier(suggestion)) setFailedSuggestion(key);
          }}>Dodaj do organizacji</button>
          {failedSuggestion === `${suggestion.identifier_type}:${suggestion.value}` && <span role="status">
            {" "}Nie udało się dodać numeru. Szczegóły są w sekcji „Numery rejestrowe” powyżej.</span>}
        </p>)}
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
  </>;

  return organizationId ? <div style={{ marginTop: 12 }}>{content}</div>
    : <CollapsibleSection title="Rejestry (CRBR, KRS, VAT, CEIDG)">{content}</CollapsibleSection>;
}
