export interface ModelOption {
  id: string;
  label: string;
  external?: boolean;
  verified?: boolean;
  context_length?: number | null;
  max_output_tokens?: number | null;
  input_price_per_million?: string | null;
  output_price_per_million?: string | null;
  currency?: string | null;
  price_source?: string | null;
  listed_by_provider?: boolean | null;
  /** true = the model honours a JSON-schema response format; false = it does not; null/undefined = unknown. */
  supports_structured_outputs?: boolean | null;
  /** false = the provider has no credentials configured: shown greyed out with `unavailable_reason`, cannot be chosen. */
  available?: boolean;
  unavailable_reason?: string | null;
  /** "deprecated" = still offered, but the provider is retiring it (`retires_on`). */
  status?: string;
  retires_on?: string | null;
}

/** A model that cannot be chosen right now (e.g. its provider has no credentials). Unknown counts as available. */
export const isModelUnavailable = (model: ModelOption): boolean => model.available === false;

const CURRENCY_SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", PLN: "zł" };

const formatTokens = (tokens: number): string =>
  tokens >= 1_000_000 ? `${+(tokens / 1_000_000).toFixed(1)} mln` : tokens >= 1000 ? `${Math.round(tokens / 1000)} tys.` : `${tokens}`;

const formatPrice = (price: string, currency: string): string => {
  const value = Number(price);
  const text = Number.isFinite(value) ? String(+value.toFixed(value < 1 ? 3 : 2)) : price;
  const symbol = CURRENCY_SYMBOLS[currency];
  return symbol && currency !== "PLN" ? `${symbol}${text}` : `${text} ${symbol ?? currency}`;
};

/** Short Polish summary of a model's price and limits ("$0.15 / $0.6 za 1 mln tok. · okno 128 tys."); "" when unknown. */
export const describeModel = (model: ModelOption): string => {
  const parts: string[] = [];
  if (isModelUnavailable(model)) parts.push(`niedostępny: ${model.unavailable_reason ?? "brak poświadczeń"}`);
  if (model.status === "deprecated") parts.push(model.retires_on ? `wycofywany (${model.retires_on})` : "wycofywany");
  if (model.listed_by_provider === false) parts.push("brak w katalogu dostawcy");
  if (model.input_price_per_million != null && model.output_price_per_million != null && model.currency) {
    parts.push(`${formatPrice(model.input_price_per_million, model.currency)} / ${formatPrice(model.output_price_per_million, model.currency)} za 1 mln tok.`);
  }
  if (model.context_length) parts.push(`okno ${formatTokens(model.context_length)}`);
  if (model.max_output_tokens) parts.push(`wyjście do ${formatTokens(model.max_output_tokens)}`);
  if (model.supports_structured_outputs === true) parts.push("schemat JSON ✓");
  if (model.supports_structured_outputs === false) parts.push("bez schematu JSON");
  return parts.join(" · ");
};

/** Option text for a model picker: the label plus the price/limit summary when known. */
export const modelOptionText = (model: ModelOption): string => {
  const details = describeModel(model);
  return details ? `${model.label} — ${details}` : model.label;
};
