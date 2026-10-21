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
}

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
  if (model.listed_by_provider === false) parts.push("brak w katalogu dostawcy");
  if (model.input_price_per_million != null && model.output_price_per_million != null && model.currency) {
    parts.push(`${formatPrice(model.input_price_per_million, model.currency)} / ${formatPrice(model.output_price_per_million, model.currency)} za 1 mln tok.`);
  }
  if (model.context_length) parts.push(`okno ${formatTokens(model.context_length)}`);
  if (model.max_output_tokens) parts.push(`wyjście do ${formatTokens(model.max_output_tokens)}`);
  return parts.join(" · ");
};

/** Option text for a model picker: the label plus the price/limit summary when known. */
export const modelOptionText = (model: ModelOption): string => {
  const details = describeModel(model);
  return details ? `${model.label} — ${details}` : model.label;
};
