import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import YoutubeFlowGuide from "./youtubeFlowGuide";
import { YOUTUBE_FLOW_DOC_URL } from "../../utils/youtubeFlow";

const readiness = (states: Record<string, string>) => ({
  status: "success",
  steps: ["content", "chunks", "embeddings", "ner", "enrichment", "tags"].map(key => ({ key, state: states[key] ?? "todo" })),
});

const renderGuide = (props: Partial<React.ComponentProps<typeof YoutubeFlowGuide>> = {}) => render(
  <MemoryRouter>
    <YoutubeFlowGuide
      docId="11274" apiUrl="http://api" apiKey="k"
      transcriptMissing={false} hasChapters hasOutline={false} {...props}
    />
  </MemoryRouter>,
);

describe("YoutubeFlowGuide", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ json: async () => readiness({ content: "done" }) })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("asks for the readiness of this document with the API key", async () => {
    renderGuide();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledWith("http://api/document/11274/readiness", { headers: { "x-api-key": "k" } });
  });

  it("shows the current stage in the summary and links each stage to its documentation section", async () => {
    renderGuide();
    await waitFor(() => expect(screen.getByText(/teraz: Chunki i przegląd/)).toBeTruthy());
    const list = screen.getByRole("list", { name: "Etapy flow pracy z tekstem" });
    const import_ = within(list).getByRole("link", { name: "Import" });
    expect(import_.getAttribute("href")).toBe(`${YOUTUBE_FLOW_DOC_URL}#flow-import`);
    expect(import_.getAttribute("target")).toBe("_blank");
    expect(import_.getAttribute("rel")).toContain("noopener");
    expect(within(list).getByRole("link", { name: "Osoby i miejsca (NER)" }).getAttribute("href"))
      .toBe(`${YOUTUBE_FLOW_DOC_URL}#flow-entities`);
  });

  it("lists what can happen next, with in-app links and the independence note", async () => {
    renderGuide();
    const ner = await screen.findByRole("link", { name: "Przejrzyj osoby, miejsca i organizacje" });
    expect(ner.getAttribute("href")).toBe("/ner/11274/1");
    expect(screen.getByRole("link", { name: "Przeanalizuj i zatwierdź chunki" }).getAttribute("href")).toBe("/chunks/11274");
    expect(screen.getByRole("note").textContent).toContain("niezależne");
  });

  it("links to the whole map", async () => {
    renderGuide();
    await screen.findByText(/teraz:/);
    const full = screen.getByRole("link", { name: /Pełna mapa flow w dokumentacji/ });
    expect(full.getAttribute("href")).toBe(YOUTUBE_FLOW_DOC_URL);
  });

  it("still renders when the readiness request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    renderGuide();
    expect(await screen.findByText("Nie udało się wczytać stanu dalszych etapów")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Etapy flow pracy z tekstem" })).toBeTruthy();
  });

  it("tells the user to fetch the transcript first when it is missing", async () => {
    renderGuide({ transcriptMissing: true, hasChapters: false });
    expect(await screen.findByText("Pobierz transkrypcję")).toBeTruthy();
    expect(screen.getByText(/teraz: Import/)).toBeTruthy();
  });
});
