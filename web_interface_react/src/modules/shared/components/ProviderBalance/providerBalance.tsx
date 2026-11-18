import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";

export type ProviderBalanceInfo = {
  provider: string; name: string; source: "api" | "estimated"; unit: string;
  status: "ok" | "not_configured" | "unavailable";
  remaining?: number | null; days_left?: number | null; low?: boolean; exhausted?: boolean;
  base_amount?: number; as_of?: string; fixed_monthly?: number; warn_days?: number; daily_burn?: number;
  spent_since?: number; unpriced_rows?: number; limit?: number | null; has_limit?: boolean;
};

const CREDITS = "kredytów";

const amount = (value: number, unit: string) =>
  unit === CREDITS
    ? `${Math.round(value).toLocaleString("pl-PL")} ${unit}`
    : `${value.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${unit}`;

/** A balance the provider reports itself (OpenRouter spending limit, Firecrawl/Serper credits). */
function ApiBalanceView({ balance }: { balance: ProviderBalanceInfo }) {
  const style = { fontSize: ".85rem" } as const;
  if (balance.status === "not_configured") {
    return <span role="status" style={{ ...style, color: "#64748b" }}>{balance.name}: brak klucza API</span>;
  }
  if (balance.status === "unavailable") {
    return <span role="status" style={{ ...style, color: "#64748b" }}>{balance.name}: nie udało się odczytać salda</span>;
  }
  if (balance.remaining == null) {
    return <span role="status" style={{ ...style, color: "#475569" }}>
      {balance.name}: klucz bez limitu{balance.spent_since != null ? ` (zużyto ${amount(balance.spent_since, balance.unit)})` : ""}
    </span>;
  }
  const warn = Boolean(balance.low || balance.exhausted);
  return <span role="status" style={{ ...style, color: balance.exhausted ? "#991b1b" : warn ? "#92400e" : "#475569", fontWeight: warn ? 600 : 400 }}>
    {balance.name}: zostało {amount(Math.max(balance.remaining, 0), balance.unit)}
    {balance.limit != null && <> z {amount(balance.limit, balance.unit)}</>}
    {balance.exhausted && <> · wyczerpane</>}
    {balance.low && !balance.exhausted && <> · mało</>}
  </span>;
}

/** Balance of a provider that has no billing API: the owner's last entered balance minus priced usage since. */
export function ProviderBalanceView({ balance }: { balance: ProviderBalanceInfo | null | undefined }) {
  if (balance === undefined) return null; // not loaded yet
  if (balance !== null && balance.source === "api") return <ApiBalanceView balance={balance} />;
  if (balance === null || balance.status === "unavailable") {
    return <span style={{ color: "#64748b", fontSize: ".85rem" }}>Saldo: brak danych</span>;
  }
  if (balance.status === "not_configured" || balance.remaining == null) {
    return <span role="status" style={{ color: "#92400e", fontSize: ".85rem" }}
      title="Dostawca nie udostępnia API salda. Wpisz ostatnie znane saldo z panelu klienta — Lenie odejmie od niego koszty z logu użycia.">
      {balance.name}: saldo nie ustawione
    </span>;
  }
  const warn = Boolean(balance.low || balance.exhausted);
  const runway = balance.days_left == null ? null : Math.round(balance.days_left);
  return <span role="status" style={{ color: balance.exhausted ? "#991b1b" : warn ? "#92400e" : "#475569", fontSize: ".85rem", fontWeight: warn ? 600 : 400 }}
    title={`Szacunek, nie dane dostawcy: saldo z ${balance.as_of} (${amount(balance.base_amount ?? 0, balance.unit)}) minus koszty zapytań od tego dnia (${amount(balance.spent_since ?? 0, balance.unit)})${balance.fixed_monthly ? `, plus stały koszt ${amount(balance.fixed_monthly, balance.unit)} miesięcznie` : ""}.`}>
    {balance.name}: ok. {amount(Math.max(balance.remaining, 0), balance.unit)} (szacunek)
    {runway != null && !balance.exhausted && <> · starczy na ok. {runway} dni</>}
    {balance.exhausted && <> · środki wyczerpane</>}
    {balance.low && !balance.exhausted && <> · mniej niż {balance.warn_days} dni zapasu</>}
  </span>;
}

function BalanceForm({ balance, onSave }: { balance: ProviderBalanceInfo; onSave: (body: Record<string, number | string>) => Promise<string | null> }) {
  const [value, setValue] = React.useState(balance.remaining != null ? String(balance.remaining) : "");
  const [asOf, setAsOf] = React.useState(new Date().toISOString().slice(0, 10));
  const [fixed, setFixed] = React.useState(String(balance.fixed_monthly ?? 0));
  const [warn, setWarn] = React.useState(String(balance.warn_days ?? 14));
  const [error, setError] = React.useState<string | null>(null);
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    const parsed = Number(value.replace(",", "."));
    if (!value.trim() || Number.isNaN(parsed)) { setError("Podaj saldo jako liczbę."); return; }
    setError(await onSave({ amount: parsed, as_of: asOf, fixed_monthly: Number(fixed.replace(",", ".")) || 0, warn_days: Number(warn) || 14 }));
  };
  return <form onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end", marginTop: 6, fontSize: ".85rem" }}>
    <label>Saldo ({balance.unit})<br /><input aria-label="Saldo" value={value} onChange={(e) => setValue(e.target.value)} size={8} /></label>
    <label>Na dzień<br /><input aria-label="Na dzień" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></label>
    <label title="Koszty portfela spoza zapytań do modeli (maszyny, storage), w jednostkach na miesiąc.">Stały koszt / mies.<br /><input aria-label="Stały koszt miesięczny" value={fixed} onChange={(e) => setFixed(e.target.value)} size={6} /></label>
    <label title="Ostrzeżenie, gdy saldo starczy na mniej dni niż ta liczba.">Ostrzegaj poniżej (dni)<br /><input aria-label="Próg w dniach" value={warn} onChange={(e) => setWarn(e.target.value)} size={4} /></label>
    <button type="submit">Zapisz saldo</button>
    {error && <span style={{ color: "#b91c1c" }}>{error}</span>}
  </form>;
}

/** Hand-entered balances (providers without a billing API), each with a collapsed form to correct the base.
 *  With `showAll` the balances the providers report themselves (OpenRouter, Firecrawl, Serper) are listed too —
 *  `/llm-costs` leaves them out because it shows OpenRouter on its own line. */
export default function ProviderBalances({ refreshKey = 0, showAll = false }: { refreshKey?: number; showAll?: boolean }) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [balances, setBalances] = React.useState<ProviderBalanceInfo[] | null | undefined>(undefined);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "", "Content-Type": "application/json" }), [apiKey]);

  const load = React.useCallback(async (isCancelled: () => boolean = () => false) => {
    try {
      const response = await fetch(`${apiUrl}/provider_balances`, { headers });
      const data = await response.json().catch(() => ({}));
      if (!isCancelled()) setBalances(response.ok ? (data.balances as ProviderBalanceInfo[]) ?? null : null);
    } catch { if (!isCancelled()) setBalances(null); }
  }, [apiUrl, headers]);

  React.useEffect(() => {
    let cancelled = false;
    void load(() => cancelled);
    return () => { cancelled = true; };
  }, [load, refreshKey]);

  const save = (provider: string) => async (body: Record<string, number | string>): Promise<string | null> => {
    try {
      const response = await fetch(`${apiUrl}/provider_balances/${provider}`, { method: "PUT", headers, body: JSON.stringify(body) });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        return response.status === 403 ? "Zapis wymaga klucza użytkownika lub serwisowego." : (data.message ?? data.description ?? "Nie udało się zapisać salda.");
      }
      await load();
      return null;
    } catch { return "Nie udało się połączyć z serwerem."; }
  };

  if (balances === undefined) return null;
  if (balances === null) return <ProviderBalanceView balance={null} />;
  return <>{balances.filter((entry) => showAll || entry.source === "estimated").map((entry) => (
    <div key={entry.provider} style={{ marginTop: 4 }}>
      <ProviderBalanceView balance={entry} />
      {entry.source === "estimated" && <details style={{ marginTop: 2 }}>
        <summary style={{ cursor: "pointer", fontSize: ".8rem", color: "#64748b" }}>Ustaw saldo {entry.name}</summary>
        <BalanceForm balance={entry} onSave={save(entry.provider)} />
      </details>}
    </div>
  ))}</>;
}
