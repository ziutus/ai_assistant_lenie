import { describe, expect, it } from "vitest";
import { describeRequestError } from "./requestError";

const now = new Date("2026-11-01T12:24:04Z");
const config = { method: "post", url: "/website_entities", baseURL: "http://192.168.200.7:5055/", timeout: 150000 };

describe("describeRequestError", () => {
  it("explains a network error with target, origin, time and a hint", () => {
    const info = describeRequestError(
      { message: "Network Error", code: "ERR_NETWORK", config },
      "Nie udało się wykryć encji",
      { now, startedAt: now.getTime() - 50, context: { Dokument: 11226 } },
    );
    expect(info.summary).toMatch(/^Nie udało się wykryć encji: brak odpowiedzi serwera/);
    expect(info.summary).toContain("adres API w /connect");
    expect(info.details).toContain("Dokument: 11226");
    expect(info.details).toContain("Żądanie: POST http://192.168.200.7:5055/website_entities");
    expect(info.details).toContain("Strona (źródło żądania): http://localhost");
    expect(info.details).toMatch(/Czas błędu: 2026-11-01 \d\d:\d\d:04 \(UTC[+-]\d\d:\d\d\)/);
    expect(info.details).toContain("Czas trwania żądania: 0.05 s");
    expect(info.details).toContain("Odpowiedź HTTP: brak");
    expect(info.details).toContain("Kod błędu klienta: ERR_NETWORK");
  });

  it("keeps the server message as the reason for an HTTP error", () => {
    const info = describeRequestError(
      { message: "Request failed with status code 409", config, response: { status: 409, data: { message: "Document has embeddings." } } },
      "Nie udało się wykryć encji",
    );
    expect(info.summary).toBe("Nie udało się wykryć encji: Document has embeddings.");
    expect(info.details).toContain("Odpowiedź HTTP: 409");
    expect(info.details).toContain("Komunikat serwera: Document has embeddings.");
  });

  it("names the status when the server sent no message (HTML error page)", () => {
    const info = describeRequestError(
      { config, response: { status: 502, statusText: "Bad Gateway", data: "<html>nginx</html>" } },
      "Nie udało się zapisać",
    );
    expect(info.summary).toBe("Nie udało się zapisać: serwer odpowiedział błędem HTTP 502 (Bad Gateway) bez komunikatu");
    expect(info.details).not.toContain("<html>");
  });

  it("describes a timeout and warns the operation may have run", () => {
    const info = describeRequestError({ code: "ECONNABORTED", message: "timeout of 150000ms exceeded", config }, "Nie udało się wykryć encji");
    expect(info.summary).toContain("po 150 s");
    expect(info.summary).toContain("mogła się jednak wykonać");
  });

  it("never leaks headers or request bodies", () => {
    const info = describeRequestError(
      { message: "Network Error", config: { ...config, headers: { "x-api-key": "lk_svc_secret" }, data: "{\"id\":1}" } },
      "Nie udało się wykryć encji",
    );
    expect(info.details).not.toContain("lk_svc_secret");
    expect(info.details).not.toContain("{\"id\":1}");
  });

  it("survives a non-error value", () => {
    expect(describeRequestError("boom", "Nie udało się").summary).toContain("Nie udało się:");
  });
});
