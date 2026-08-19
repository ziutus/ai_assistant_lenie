import axios from "axios";
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthorizationState } from "../../../types";
import { AuthorizationContext } from "../context/authorizationContext";
import List from "./list";

vi.mock("axios");
const mockedGet = axios.get as unknown as ReturnType<typeof vi.fn>;

const auth: AuthorizationState = {
  apiUrl: "http://api.test", apiKey: "service-key", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "obsidian_note", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "ALL", setSelectedDocumentState: vi.fn(),
};

const obsidianNoteItem = {
  id: 10315,
  title: "Kubernetes — podstawy",
  url: "obsidian://02-wiedza/Informatyka/k8s.md",
  document_type: "obsidian_note",
  processing_status: "EMBEDDING_EXIST",
  processing_error_code: "NONE",
  byline: null,
  groups: [],
};

describe("List — obsidian_note row actions", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: () => Promise.resolve({ content_groups: [] }) }));
    mockedGet.mockReset().mockImplementation((url: string) => {
      if (url.endsWith("/document_states")) {
        return Promise.resolve({ data: { states: ["ALL"], types: ["obsidian_note"], errors: [] } });
      }
      if (url.endsWith("/website_list")) {
        return Promise.resolve({ data: { websites: [obsidianNoteItem], all_results_count: 1 } });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
  });

  it("shows Czytaj/Chunki (real text_md, no processing pipeline) but not Edit (no /obsidian_note/:id route)", async () => {
    render(
      <AuthorizationContext.Provider value={auth}>
        <MemoryRouter initialEntries={["/list?type=obsidian_note"]}>
          <List />
        </MemoryRouter>
      </AuthorizationContext.Provider>,
    );

    const readLink = await screen.findByRole("link", { name: "Czytaj" });
    expect(readLink.getAttribute("href")).toBe("/read/10315");
    expect(screen.getByRole("link", { name: "Chunki" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Edit" })).toBeNull();
  });
});
