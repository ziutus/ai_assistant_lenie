import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AuthorizationState } from "../../../types";
import { AuthorizationContext } from "../context/authorizationContext";
import Chunks from "./chunks";

const auth: AuthorizationState = {
  apiUrl: "http://api.test", apiKey: "test-key", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "link", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "NEED_MANUAL_REVIEW", setSelectedDocumentState: vi.fn(),
};
const completed = /Proces zakończony — dokument znajduje się w indeksie/;

function renderCompletedRun() {
  const chunk = {
    id: 11, position: 1, type: "TEMAT", status: "approved", topic: "Temat testowy",
    original_text: "Tekst testowy", corrected_text: null, has_embeddings: true,
    obsidian_note_paths: [], obsidian_note_not_needed: false,
  };
  const run = { id: 7, status: "reviewed", mode: "article", chunk_count: 1 };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input)).pathname;
    let data: unknown = {};
    if (path === "/analysis_runs") data = { runs: [run] };
    if (path === "/analysis_run/7/chunks") data = {
      run, chunks: [chunk], document: { document_type: "webpage", processing_status: "EMBEDDING_EXIST" },
    };
    if (path === "/website_get") data = {
      title: "Dokument testowy", document_type: "webpage", processing_status: "EMBEDDING_EXIST",
    };
    if (path === "/chunk/11" && init?.method === "PATCH") data = {
      status: "success", chunk: { ...chunk, ...JSON.parse(String(init.body)), has_embeddings: null },
    };
    if (path === "/analysis_run/7/mark_notes_not_needed") data = { status: "success", chunks_changed: 1 };
    return new Response(JSON.stringify(data), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <AuthorizationContext.Provider value={auth}>
      <MemoryRouter initialEntries={["/chunks/42"]}>
        <Routes><Route path="/chunks/:id" element={<Chunks />} /></Routes>
      </MemoryRouter>
    </AuthorizationContext.Provider>,
  );
  return fetchMock;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("Completed chunk review", () => {
  it("marks and unmarks a chunk without losing the completed panel after a PATCH with null embeddings", async () => {
    const fetchMock = renderCompletedRun();
    await screen.findByText(completed);
    fireEvent.click(screen.getByRole("button", { name: "Pokaż wynikowe chunki" }));
    fireEvent.click(screen.getByText("oznacz: bez notatki"));
    fireEvent.click(await screen.findByText("🚫📝 bez notatki"));
    await screen.findByText("oznacz: bez notatki");
    expect(screen.getByText(completed)).toBeTruthy();
    const writes = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(writes.map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
      { obsidian_note_not_needed: true }, { obsidian_note_not_needed: false },
    ]);
    expect(fetchMock.mock.calls.some(([url]) => /generate_embeddings|reopen_review/.test(String(url)))).toBe(false);
  });

  it("marks the remaining chunks in a completed run and hides the bulk action", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = renderCompletedRun();
    await screen.findByText(completed);
    fireEvent.click(screen.getByRole("button", { name: "Pozostałe bez notatki" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Pozostałe bez notatki" })).toBeNull());
    expect(screen.getByText(completed)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/analysis_run/7/mark_notes_not_needed",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ value: true }) }));
    fireEvent.click(screen.getByRole("button", { name: "Pokaż wynikowe chunki" }));
    expect(screen.getByText("🚫📝 bez notatki")).toBeTruthy();
  });
});
