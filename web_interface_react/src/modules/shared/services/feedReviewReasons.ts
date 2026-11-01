import { describeRequestError } from "../utils/requestError";

export type FeedReviewReason = {
  code: string; label: string; sort_order: number; system: boolean;
  selectable: boolean; active: boolean; usage_count: number;
};

export async function reasonsRequest(url: string, apiKey: string, method = "GET", body?: object) {
  const startedAt = Date.now();
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 20_000);
  let response: Response | undefined;
  let data: { reasons?: FeedReviewReason[]; message?: string } = {};
  try {
    response = await fetch(url, {
      method, headers: { "x-api-key": apiKey, "Content-Type": "application/json" },
      signal: controller.signal, ...(body ? { body: JSON.stringify(body) } : {}),
    });
    data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error("HTTP error");
    if (method === "GET" && !Array.isArray(data.reasons)) throw new Error("Invalid catalog response");
    return data;
  } catch (cause) {
    console.error("Feed review reasons request failed", cause);
    throw describeRequestError({
      config: { method, url, timeout: 20_000 },
      code: controller.signal.aborted ? "ECONNABORTED" : "ERR_NETWORK",
      ...(response ? { response: { status: response.status, data: response.status === 403
        ? { message: "Zapis powodów pominięcia wymaga klucza service." } : data } } : {}),
    }, method === "GET" ? "Nie udało się pobrać powodów pominięcia" : "Nie udało się zapisać powodów pominięcia", { startedAt });
  } finally { window.clearTimeout(timer); }
}
