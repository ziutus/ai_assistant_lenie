import axios from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { probeBackend } from "./backendProbe";

vi.mock("axios");

beforeEach(() => {
  vi.resetAllMocks();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("probeBackend", () => {
  it("says the backend is alive when /healthz answers, so only the request failed", async () => {
    vi.mocked(axios.get).mockResolvedValue({ status: 200 });
    const lines = await probeBackend("http://nas:5055/");
    expect(axios.get).toHaveBeenCalledWith("http://nas:5055/healthz", expect.objectContaining({ timeout: 4000 }));
    expect(lines.join("\n")).toContain("Sonda GET http://nas:5055/healthz: backend odpowiada (HTTP 200");
    expect(lines.join("\n")).toContain("Padło więc samo to żądanie");
  });

  it("reports a CORS block when only the no-cors fetch gets through", async () => {
    vi.mocked(axios.get).mockRejectedValue(new Error("Network Error"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ type: "opaque" }));
    const text = (await probeBackend("http://nas:5055")).join("\n");
    expect(text).toContain("serwer jest osiągalny");
    expect(text).toContain("CORS");
  });

  it("reports an unreachable backend when both probes fail", async () => {
    vi.mocked(axios.get).mockRejectedValue(new Error("Network Error"));
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const text = (await probeBackend("http://nas:5055")).join("\n");
    expect(text).toContain("backend albo NAS jest nieosiągalny");
    expect(text).toContain("To nie jest problem z danymi dokumentu");
  });

  it("notes that the browser itself is offline", async () => {
    vi.mocked(axios.get).mockRejectedValue(new Error("Network Error"));
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    vi.stubGlobal("navigator", { onLine: false });
    const text = (await probeBackend("http://nas:5055")).join("\n");
    expect(text).toContain("navigator.onLine = false");
  });
});
