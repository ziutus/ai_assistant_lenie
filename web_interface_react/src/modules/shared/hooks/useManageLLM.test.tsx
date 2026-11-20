import axios from "axios";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useManageLLM } from "./useManageLLM";

const navigate = vi.fn();
vi.mock("axios");
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key", apiType: "Docker" }) };
});

const youtube = { id: 42, document_type: "youtube", title: "Film", text: "## Wstęp\n\nTekst." };
const hook = () => renderHook(() => useManageLLM({ formik: {}, selectedDocumentType: "youtube", selectedDocumentState: "ALL" }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.post).mockResolvedValue({ data: { message: "Zapisano" } });
});
afterEach(() => navigate.mockReset());

it("saves a YouTube transcript for manual review and continues to the first chapter's NER review by default", async () => {
  const { result } = hook();
  await act(async () => { await result.current.handleSaveWebsiteNext(youtube); });
  expect(axios.post).toHaveBeenCalledWith("/website_save", expect.objectContaining({
    id: 42, document_type: "youtube", processing_status: "NEED_MANUAL_REVIEW",
  }), expect.any(Object));
  expect(navigate).toHaveBeenCalledWith("/ner/42/1");
});

it("can skip the NER review and go straight to the chunk analysis, with the same save", async () => {
  const { result } = hook();
  await act(async () => { await result.current.handleSaveWebsiteNext(youtube, "chunks"); });
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(axios.post).toHaveBeenCalledWith("/website_save", expect.objectContaining({
    id: 42, processing_status: "NEED_MANUAL_REVIEW",
  }), expect.any(Object));
  expect(navigate).toHaveBeenCalledWith("/chunks/42");
});

it("does not navigate when saving fails", async () => {
  vi.mocked(axios.post).mockRejectedValue(new Error("boom"));
  vi.spyOn(console, "error").mockImplementation(() => {});
  const { result } = hook();
  await act(async () => { await result.current.handleSaveWebsiteNext(youtube, "ner"); });
  expect(navigate).not.toHaveBeenCalled();
});

const networkError = () => Object.assign(new Error("Network Error"), {
  isAxiosError: true,
  code: "ERR_NETWORK",
  config: { method: "post", url: "/website_save" },
});

it("explains a failed save in Polish with technical details and says the backend is alive", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(axios.post).mockRejectedValue(networkError());
  vi.mocked(axios.get).mockResolvedValue({ status: 200 });
  const { result } = hook();
  await act(async () => { await result.current.handleSaveWebsiteToCorrect(youtube); });
  expect(result.current.isError).toBe(true);
  expect(result.current.message).toMatch(/^Nie udało się zapisać dokumentu: brak odpowiedzi serwera/);
  expect(result.current.message).not.toContain("There was an error");
  const details = result.current.errorDetails;
  expect(details).toContain("Dokument: 42");
  expect(details).toContain("Rozmiar zapisywanych danych:");
  expect(details).toContain("Żądanie: POST /website_save");
  expect(details).toContain("Kod błędu klienta: ERR_NETWORK");
  expect(details).toContain("Sonda GET /healthz: backend odpowiada");
  expect(details).not.toContain("test-key");
  expect(result.current.isLoading).toBe(false);
});

it("reports an unreachable backend when the probe fails too", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  vi.mocked(axios.post).mockRejectedValue(networkError());
  vi.mocked(axios.get).mockRejectedValue(new Error("Network Error"));
  const { result } = hook();
  await act(async () => { await result.current.handleSaveWebsiteToCorrect(youtube); });
  expect(result.current.errorDetails).toContain("backend albo NAS jest nieosiągalny");
  vi.unstubAllGlobals();
});

it("does not probe the backend when the server answered with an HTTP error", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(axios.post).mockRejectedValue(Object.assign(new Error("Request failed with status code 413"), {
    isAxiosError: true,
    config: { method: "post", url: "/website_save" },
    response: { status: 413, statusText: "Payload Too Large", data: "<html>nginx</html>" },
  }));
  const { result } = hook();
  await act(async () => { await result.current.handleSaveWebsiteToCorrect(youtube); });
  expect(axios.get).not.toHaveBeenCalled();
  expect(result.current.message).toContain("HTTP 413 (Payload Too Large)");
  expect(result.current.errorDetails).toContain("Odpowiedź HTTP: 413 Payload Too Large");
});

it("drops stale details once a newer message replaces the error", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.mocked(axios.post).mockRejectedValueOnce(networkError());
  vi.mocked(axios.get).mockResolvedValue({ status: 200 });
  const { result } = hook();
  await act(async () => { await result.current.handleSaveWebsiteToCorrect(youtube); });
  expect(result.current.errorDetails).not.toBe("");
  vi.mocked(axios.post).mockResolvedValueOnce({ data: { message: "Zapisano" } });
  await act(async () => { await result.current.handleSaveWebsiteToCorrect(youtube); });
  expect(result.current.message).toBe("Zapisano");
  expect(result.current.errorDetails).toBe("");
});
