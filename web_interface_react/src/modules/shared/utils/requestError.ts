/**
 * Turns a failed HTTP request (axios) into a short Polish message for the user
 * plus a block of technical details that is easy to paste into a bug report.
 *
 * Rule of thumb (see AGENTS.md, "Error messages"): the summary says what the
 * user was doing and why it failed; the details say everything an engineer needs
 * to reproduce it without asking — what was requested, from where, to where, when,
 * how long it took and what came back. Never put the API key or a request body
 * in either of them.
 */

export interface RequestErrorInfo {
  /** One line for the user: "<what failed>: <why>". */
  summary: string;
  /** Multi-line plain text for the "Szczegóły techniczne" disclosure. */
  details: string;
}

export interface RequestErrorOptions {
  /** `Date.now()` taken just before the request; adds the elapsed time. */
  startedAt?: number;
  /** Extra identifying facts, e.g. `{ dokument: 11226 }`; empty values are skipped. */
  context?: Record<string, string | number | null | undefined>;
  /** Clock override for tests. */
  now?: Date;
}

interface AxiosLikeError {
  message?: string;
  code?: string;
  config?: { method?: string; url?: string; baseURL?: string; timeout?: number };
  response?: { status?: number; statusText?: string; data?: unknown };
}

const pad = (value: number) => String(value).padStart(2, "0");

function localTimestamp(date: Date): string {
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())} `
    + `(UTC${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)})`;
}

function serverMessage(data: unknown): string | null {
  if (data && typeof data === "object") {
    const message = (data as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message.trim();
  }
  if (typeof data === "string" && data.trim() && !data.trimStart().startsWith("<")) {
    return data.trim().slice(0, 300);
  }
  return null;
}

function requestedUrl(config: AxiosLikeError["config"]): string {
  const url = config?.url ?? "";
  if (/^https?:\/\//i.test(url)) return url;
  return `${(config?.baseURL ?? "").replace(/\/$/, "")}${url}` || "(nieznany adres)";
}

/** Why the request failed, in words, without the technical vocabulary. */
function reason(error: AxiosLikeError): string {
  if (error.response) {
    const fromServer = serverMessage(error.response.data);
    if (fromServer) return fromServer;
    return `serwer odpowiedział błędem HTTP ${error.response.status ?? "?"}`
      + `${error.response.statusText ? ` (${error.response.statusText})` : ""} bez komunikatu`;
  }
  if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT" || /timeout/i.test(error.message ?? "")) {
    const seconds = error.config?.timeout ? ` po ${Math.round(error.config.timeout / 1000)} s` : "";
    return `serwer nie odpowiedział w limicie czasu${seconds}. Operacja mogła się jednak wykonać — odśwież listę`;
  }
  if (error.code === "ERR_CANCELED") return "żądanie zostało anulowane";
  return "brak odpowiedzi serwera — żądanie nie dotarło do backendu albo odpowiedź została zablokowana. "
    + "Sprawdź połączenie z siecią i adres API w /connect, odśwież stronę i spróbuj ponownie";
}

export function describeRequestError(
  error: unknown,
  operation: string,
  options: RequestErrorOptions = {},
): RequestErrorInfo {
  const err: AxiosLikeError = error && typeof error === "object" ? (error as AxiosLikeError) : { message: String(error) };
  const now = options.now ?? new Date();
  const summary = `${operation}: ${reason(err)}`;

  const lines: string[] = [`Operacja: ${operation}`];
  for (const [key, value] of Object.entries(options.context ?? {})) {
    if (value !== null && value !== undefined && value !== "") lines.push(`${key}: ${value}`);
  }
  if (err.config) {
    lines.push(`Żądanie: ${(err.config.method ?? "get").toUpperCase()} ${requestedUrl(err.config)}`);
  }
  const origin = typeof window !== "undefined" ? window.location?.origin : undefined;
  if (origin) lines.push(`Strona (źródło żądania): ${origin}${window.location.pathname}`);
  lines.push(`Czas błędu: ${localTimestamp(now)}`);
  if (options.startedAt !== undefined) {
    lines.push(`Czas trwania żądania: ${((now.getTime() - options.startedAt) / 1000).toFixed(2)} s`);
  }
  if (err.response) {
    lines.push(`Odpowiedź HTTP: ${err.response.status ?? "?"}${err.response.statusText ? ` ${err.response.statusText}` : ""}`);
    const body = serverMessage(err.response.data);
    if (body) lines.push(`Komunikat serwera: ${body}`);
  } else {
    lines.push("Odpowiedź HTTP: brak");
  }
  if (err.code) lines.push(`Kod błędu klienta: ${err.code}`);
  if (err.message) lines.push(`Komunikat klienta: ${err.message}`);
  return { summary, details: lines.join("\n") };
}
