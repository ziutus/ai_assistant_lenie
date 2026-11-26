import React from "react";
import axios from "axios";
import CompanyRegistryResult, { type Result } from "./CompanyRegistryResult";
import RequestErrorDetails from "./RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../utils/requestError";
import { probeBackend } from "../utils/backendProbe";
import type { IdentifierInput } from "./OrganizationIdentifiers";

export default function CompanyRegistryPanel({ apiUrl, headers, organizationId,
  identifiers = [], onAddIdentifier, onIdentifiersChanged, onOrganizationChanged, savingIdentifier }: {
  apiUrl: string; headers: Record<string, string>; organizationId: number;
  identifiers?: IdentifierInput[]; onAddIdentifier?: (input: IdentifierInput) => Promise<boolean>; savingIdentifier?: boolean;
  onIdentifiersChanged?: () => void; onOrganizationChanged?: () => void;
}) {
  const [busy, setBusy] = React.useState(false);
  const [result, setResult] = React.useState<Result | null>(null);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);

  async function check() {
    setBusy(true); setError(null); setResult(null);
    const startedAt = Date.now();
    try {
      const response = await axios.post<Result>(`${apiUrl}/organizations/${organizationId}/identifiers/sync`, {},
        { headers: { ...headers, "Content-Type": "application/json" }, timeout: 180000 });
      setResult(response.data);
      if (response.data.identifier_sync?.added.length) onIdentifiersChanged?.();
      if (response.data.seat?.country_added || response.data.seat?.address_added) onOrganizationChanged?.();
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

  return <div style={{ marginTop: 12 }}>
    <button disabled={busy || savingIdentifier} onClick={() => void check()}>
      {busy ? "Sprawdzanie…" : "🔎 Sprawdź w rejestrach (CRBR, KRS, VAT, CEIDG)"}</button>
    {error && <div role="alert"><p>{error.summary}</p><RequestErrorDetails details={error.details} /></div>}
    {result && <CompanyRegistryResult result={result} identifiers={identifiers}
      onAddIdentifier={onAddIdentifier} savingIdentifier={savingIdentifier} />}
  </div>;
}
