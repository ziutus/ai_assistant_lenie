import React from "react";
import { AuthorizationContext } from "../../context/authorizationContext";

export type OpenRouterBalanceInfo = {
  status: "ok" | "not_configured" | "unavailable";
  has_limit?: boolean; limit_usd?: number | null; remaining_usd?: number | null; usage_usd?: number | null;
  reset?: string | null; free_tier?: boolean; low?: boolean; exhausted?: boolean;
};

const RESET_TEXT: Record<string, string> = { daily: "dzienny", weekly: "tygodniowy", monthly: "miesięczny" };
const usd = (value: number) =>
  `${value.toLocaleString("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: value < 1 ? 4 : 2 })} USD`;

/** What is left of the OpenRouter key's spending limit; amber when it runs low, red when it is used up. */
export function OpenRouterBalanceView({ balance }: { balance: OpenRouterBalanceInfo | null | undefined }) {
  if (balance === undefined || balance?.status === "not_configured") return null; // not loaded yet / OpenRouter not used
  if (balance === null || balance.status === "unavailable") {
    return <span style={{ color: "#64748b", fontSize: ".85rem" }} title="Nie udało się zapytać OpenRouter o limit klucza.">OpenRouter: brak danych o saldzie</span>;
  }
  if (!balance.has_limit || balance.remaining_usd == null || balance.limit_usd == null) {
    return <span role="status" style={{ color: "#92400e", fontSize: ".85rem" }}
      title="Klucz OpenRouter nie ma ustawionego limitu wydatków, więc nie da się pokazać, ile zostało. Ustaw limit klucza w panelu OpenRouter — wtedy pojawi się tu saldo, a OpenRouter sam zatrzyma zapytania po jego wyczerpaniu.">
      OpenRouter: klucz bez limitu{balance.usage_usd != null && <> · zużyto {usd(balance.usage_usd)}</>}
    </span>;
  }
  const warn = Boolean(balance.low || balance.exhausted);
  const reset = balance.reset ? RESET_TEXT[balance.reset] ?? balance.reset : null;
  return <span role="status" style={{ color: balance.exhausted ? "#991b1b" : warn ? "#92400e" : "#475569", fontSize: ".85rem", fontWeight: warn ? 600 : 400 }}
    title="Limit wydatków klucza OpenRouter używanego przez Lenie (z odpowiedzi OpenRouter, odświeżane co minutę). Gdy się wyczerpie, OpenRouter odrzuca zapytania.">
    OpenRouter: zostało {usd(Math.max(balance.remaining_usd, 0))} z {usd(balance.limit_usd)}
    {reset && <> (limit {reset})</>}
    {balance.exhausted && <> · limit wyczerpany — zapytania do modeli OpenRouter będą odrzucane</>}
    {balance.low && !balance.exhausted && <> · środki na wyczerpaniu</>}
  </span>;
}

/** Loads the balance once and again whenever ``refreshKey`` changes (for example after a paid request). */
export default function OpenRouterBalance({ refreshKey = 0 }: { refreshKey?: number }) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [balance, setBalance] = React.useState<OpenRouterBalanceInfo | null | undefined>(undefined);
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(`${apiUrl}/openrouter_balance`, { headers: { "x-api-key": apiKey ?? "" } });
        const data = await response.json().catch(() => ({}));
        if (!cancelled) setBalance(response.ok ? (data.balance as OpenRouterBalanceInfo | null) ?? null : null);
      } catch { if (!cancelled) setBalance(null); }
    })();
    return () => { cancelled = true; };
  }, [apiUrl, apiKey, refreshKey]);
  return <OpenRouterBalanceView balance={balance} />;
}
