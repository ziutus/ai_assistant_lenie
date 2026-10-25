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
