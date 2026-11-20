import axios from "axios";

/**
 * Runs right after a request failed WITHOUT any HTTP response ("Network Error",
 * a timeout) and answers the one question the bare error cannot: is the backend
 * down, or did only that one request fail?
 *
 * `/healthz` is exempt from the API key check and carries no data, so probing it
 * is safe. Two probes tell the cases apart:
 *  1. a normal CORS request (axios) — what the app itself could do;
 *  2. only if that fails, a `no-cors` fetch — it resolves (opaque) whenever the
 *     server is reachable at all, even when the browser blocks reading the answer.
 *
 * Returns plain lines for the "Szczegóły techniczne" block (no key, no headers).
 */

const PROBE_TIMEOUT_MS = 4000;

async function reachableWithoutCors(url: string): Promise<boolean> {
  if (typeof fetch !== "function") return false;
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS) : null;
  try {
    await fetch(url, { mode: "no-cors", cache: "no-store", signal: controller?.signal });
    return true;
  } catch {
    return false;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function probeBackend(apiUrl: string): Promise<string[]> {
  const lines: string[] = [];
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    lines.push("Sieć przeglądarki: brak połączenia (navigator.onLine = false) — to komputer jest offline, nie backend");
  }
  const target = `${apiUrl.replace(/\/$/, "")}/healthz`;
  const started = Date.now();
  const seconds = () => ((Date.now() - started) / 1000).toFixed(2);

  try {
    const response = await axios.get(target, { timeout: PROBE_TIMEOUT_MS });
    if (response && response.status >= 200 && response.status < 300) {
      lines.push(
        `Sonda GET ${target}: backend odpowiada (HTTP ${response.status}, ${seconds()} s). `
        + "Padło więc samo to żądanie, nie cały backend. Najczęstsze przyczyny: zbyt duże żądanie odrzucone "
        + "przez proxy (HTTP 413), połączenie przerwane w trakcie (restart/wdrożenie backendu, zamknięty "
        + "kontener) albo błąd backendu bez nagłówków CORS w odpowiedzi — sprawdź logi backendu z tej minuty",
      );
      return lines;
    }
    if (response) {
      lines.push(`Sonda GET ${target}: HTTP ${response.status} (${seconds()} s)`);
      return lines;
    }
  } catch {
    // fall through to the no-cors probe
  }

  if (await reachableWithoutCors(target)) {
    lines.push(
      `Sonda GET ${target}: serwer jest osiągalny, ale przeglądarka blokuje odczyt odpowiedzi (CORS) — `
      + "adres API w /connect nie zgadza się z tym, z którego otwarto stronę, albo proxy gubi nagłówki CORS",
    );
  } else {
    lines.push(
      `Sonda GET ${target}: brak odpowiedzi w ${PROBE_TIMEOUT_MS / 1000} s — backend albo NAS jest `
      + "nieosiągalny (kontener padł, NAS się restartuje, zły adres w /connect albo brak sieci/VPN). "
      + "To nie jest problem z danymi dokumentu",
    );
  }
  return lines;
}
