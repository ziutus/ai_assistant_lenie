import axios from "axios";
import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  has_text_md: true,
  byline: null,
  groups: [],
};

const textItemWithMarkdown = {
  id: 10430,
  title: "Wiadomość z tekstem",
  url: "whatsapp://example/message",
  document_type: "text",
  processing_status: "URL_ADDED",
  processing_error_code: "NONE",
  has_text_md: true,
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
    expect(readLink.getAttribute("href")).toBe("/read/10315?list=type%3Dobsidian_note");
    expect(screen.getByRole("link", { name: "Chunki" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Edit" })).toBeNull();
  });

  it("shows Czytaj for a text document with markdown even when its status is URL_ADDED", async () => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith("/document_states")) {
        return Promise.resolve({ data: { states: ["ALL"], types: ["text"], errors: [] } });
      }
      if (url.endsWith("/website_list")) {
        return Promise.resolve({ data: { websites: [textItemWithMarkdown], all_results_count: 1 } });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });

    render(
      <AuthorizationContext.Provider value={{ ...auth, selectedDocumentType: "text" }}>
        <MemoryRouter initialEntries={["/list?type=text"]}>
          <List />
        </MemoryRouter>
      </AuthorizationContext.Provider>,
    );

    expect((await screen.findByRole("link", { name: "Czytaj" })).getAttribute("href")).toBe("/read/10430?list=type%3Dtext");
    expect(screen.getByRole("link", { name: "Chunki" })).toBeTruthy();
  });

  it.each([null, undefined, "NONE", "EMBEDDING_ERROR"])("renders status with error code %s", async (errorCode) => {
    mockedGet.mockImplementation((url: string) => {
      if (url.endsWith("/document_states")) {
        return Promise.resolve({ data: { states: ["ALL"], types: ["obsidian_note"], errors: [] } });
      }
      if (url.endsWith("/website_list")) {
        return Promise.resolve({ data: {
          websites: [{ ...obsidianNoteItem, processing_error_code: errorCode }], all_results_count: 1,
        } });
      }
      return Promise.reject(new Error(`unexpected GET ${url}`));
    });
    render(
      <AuthorizationContext.Provider value={auth}>
        <MemoryRouter initialEntries={["/list?type=obsidian_note"]}>
          <List />
        </MemoryRouter>
      </AuthorizationContext.Provider>,
    );
    const status = await screen.findByText(/EMBEDDING_EXIST/);
    expect(status.textContent?.trim()).toBe(
      errorCode === "EMBEDDING_ERROR" ? "EMBEDDING_EXIST | EMBEDDING_ERROR" : "EMBEDDING_EXIST",
    );
  });
});


describe("List telemetry", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: async () => ({ content_groups: [] }) }));
    mockedGet.mockReset().mockImplementation((url: string) => Promise.resolve({ data:
      url.endsWith("/website_list") ? { websites: [], all_results_count: 0 }
        : { states: ["ALL"], types: ["obsidian_note"], errors: [] },
    }));
  });

  it("sends initial remembered/url origins then manual application with a fresh event and browse", async () => {
    localStorage.setItem("lenie_listFilters", JSON.stringify({ obsidianFilter: "missing" }));
    render(<AuthorizationContext.Provider value={auth}>
      <MemoryRouter initialEntries={["/list?type=obsidian_note"]}><List /></MemoryRouter>
    </AuthorizationContext.Provider>);
    await waitFor(() => expect(mockedGet.mock.calls.some(([url]) => url.endsWith("/website_list"))).toBe(true));
    const params = () => mockedGet.mock.calls.filter(([url]) => url.endsWith("/website_list")).at(-1)![1].params;
    const first = params();
    expect(first._tel_action).toBe("initial_load");
    expect(JSON.parse(first._tel_criteria_origin)).toMatchObject({
      document_type: "url", only_missing_obsidian_notes: "remembered", sort: "default",
    });
    await waitFor(() => expect(screen.getByLabelText(/Notatki Obsidian/).hasAttribute("disabled")).toBe(false));
    fireEvent.change(screen.getByLabelText(/Notatki Obsidian/), { target: { value: "has" } });
    await waitFor(() => expect(params()._tel_action).toBe("filter_change"));
    expect(JSON.parse(params()._tel_criteria_origin).only_has_obsidian_notes).toBe("manual");
    expect(JSON.parse(params()._tel_changed_fields)).toEqual(["only_missing_obsidian_notes", "only_has_obsidian_notes"]);
    expect(params()._tel_event_id).not.toBe(first._tel_event_id);
    expect(params()._tel_browse_id).not.toBe(first._tel_browse_id);
    expect(params()._tel_session_id).toBe(first._tel_session_id);
    localStorage.clear();
  });
});
