import React from "react";

export type GithubRateInfo = { limit: number | null; remaining: number | null; reset: string | null; authenticated: boolean };

const LOW_SHARE = 0.1;
const LOW_COUNT = 10;
const numberFormat = new Intl.NumberFormat("pl-PL");

/** How many GitHub requests are left this hour; amber when it runs low or when no token is configured. */
export default function GithubRate({ rate }: { rate: GithubRateInfo | null | undefined }) {
  if (rate === undefined) return null; // not loaded yet
  if (rate === null || rate.limit === null || rate.remaining === null) {
    return <span style={{ color: "#64748b", fontSize: ".85rem" }} title="Nie udało się zapytać GitHuba o limit zapytań.">GitHub: brak danych o limicie</span>;
  }
  const low = rate.remaining < LOW_COUNT || rate.remaining / rate.limit < LOW_SHARE;
  const resetAt = rate.reset ? new Date(rate.reset) : null;
  const resetText = resetAt && !Number.isNaN(resetAt.getTime())
    ? resetAt.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" }) : null;
  const warn = low || !rate.authenticated;
  return <span role="status" style={{ color: warn ? "#92400e" : "#475569", fontSize: ".85rem", fontWeight: warn ? 600 : 400 }}
    title={rate.authenticated
      ? "Zapytania do API GitHuba pozostałe w tej godzinie (z tokenu GITHUB_TOKEN). Każde odświeżenie repozytorium zużywa 1."
      : "Brak tokenu GITHUB_TOKEN w konfiguracji — obowiązuje niski limit dla zapytań anonimowych. Token podnosi go do 5000 na godzinę."}>
    GitHub: pozostało {numberFormat.format(rate.remaining)} / {numberFormat.format(rate.limit)}
    {resetText && <> · reset o {resetText}</>}
    {!rate.authenticated && <> · bez tokenu</>}
    {low && rate.authenticated && <> · limit na wyczerpaniu</>}
  </span>;
}
