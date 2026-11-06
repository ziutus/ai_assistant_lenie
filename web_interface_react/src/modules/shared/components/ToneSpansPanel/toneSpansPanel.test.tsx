import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import type { AuthorizationState } from "../../../../types";
import { AuthorizationContext } from "../../context/authorizationContext";
import type { ToneSpan } from "../../utils/toneSpans";
import ToneSpansPanel from "./toneSpansPanel";

vi.mock("axios");
const mocked = vi.mocked(axios, true);

afterEach(() => { cleanup(); vi.resetAllMocks(); });

const auth: AuthorizationState = {
  apiUrl: "http://api", apiKey: "k", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "link", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "NEED_MANUAL_REVIEW", setSelectedDocumentState: vi.fn(),
};

const span = (over: Partial<ToneSpan> = {}): ToneSpan => ({
  id: 1, chapter_position: 2, role: "outlier", label: "złośliwy", quote: "Nasz wielki ekspert znów wie lepiej.",
  note: "docinek", importance: null, status: "proposed", model: "m", ...over,
});

const renderPanel = (spans: ToneSpan[], over: Record<string, unknown> = {}) => {
  const props = {
    docId: "5", currentChapter: 2, compact: false, spans, highlight: true,
    onSpansChange: vi.fn(), onHighlightChange: vi.fn(), onToneChanged: vi.fn(), ...over,
  };
  render(<AuthorizationContext.Provider value={auth}><ToneSpansPanel {...props} /></AuthorizationContext.Provider>);
  return props;
};

describe("ToneSpansPanel", () => {
  it("lists only the passages of the chapter on screen, with role, label and note", () => {
    renderPanel([
      span({ id: 1 }),
      span({ id: 2, chapter_position: 3, quote: "Fragment z innego rozdziału." }),
      span({ id: 3, role: "key", label: "kluczowy", quote: "Sedno sprawy jest tutaj.", importance: 3, note: null }),
    ]);

    expect(screen.getByText(/Nasz wielki ekspert/)).toBeTruthy();
    expect(screen.getByText(/Sedno sprawy/)).toBeTruthy();
    expect(screen.queryByText(/innego rozdziału/)).toBeNull();
    expect(screen.getByText(/waga 3\/3/)).toBeTruthy();
    expect(screen.getByText("🔦 Wyróżnione fragmenty (2)")).toBeTruthy();
  });

  it("does nothing by itself: no request is made until a button is clicked", () => {
    renderPanel([]);

    expect(mocked.get).not.toHaveBeenCalled();
    expect(mocked.post).not.toHaveBeenCalled();
  });

  it("detects on request with the chosen model and replaces the chapter's passages", async () => {
    mocked.get.mockResolvedValue({ data: {
      default_model: "Bielik-11B-v3.0-Instruct", saved: false,
      models: [{ id: "Bielik-11B-v3.0-Instruct", label: "Bielik" }, { id: "gemini-3.1-flash-lite", label: "Gemini" }],
    } });
    mocked.post.mockResolvedValue({ data: {
      model: "gemini-3.1-flash-lite", spans: [span({ id: 9, quote: "Nowy fragment złośliwy w tekście." })],
      report: { fragments: 3, rejected_no_quote: 1, llm_cost_amount: "0.002", llm_cost_currency: "USD" },
    } });
    const other = span({ id: 7, chapter_position: 5, quote: "Fragment z rozdziału piątego." });
    const props = renderPanel([span({ id: 1 }), other]);

    const summary = screen.getByText(/^Model: /);
    const details = summary.closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    await screen.findByRole("option", { name: "Gemini" });
    fireEvent.change(screen.getByLabelText("Model do analizy rozdziału"), { target: { value: "gemini-3.1-flash-lite" } });
    fireEvent.click(screen.getByRole("button", { name: /Wykryj fragmenty/ }));

    await waitFor(() => expect(props.onSpansChange).toHaveBeenCalled());
    expect(mocked.post.mock.calls[0][0]).toBe("http://api/document/5/chapter/2/detect_tone_spans");
    expect(mocked.post.mock.calls[0][1]).toEqual({ model: "gemini-3.1-flash-lite" });
    expect(props.onSpansChange.mock.calls[0][0].map((s: ToneSpan) => s.id)).toEqual([7, 9]);
    const status = screen.getByRole("status").textContent ?? "";
    expect(status).toContain("w 3 częściach");
    expect(status).toContain("odrzucono 1 z cytatem, którego nie ma w tekście");
    expect(status).toContain("koszt 0.0020 USD");
  });

  it("asks for the whole document in a compact reader and replaces every passage", async () => {
    mocked.post.mockResolvedValue({ data: { model: "m", spans: [span({ id: 9, chapter_position: 1 })], report: {} } });
    const props = renderPanel([span({ id: 1 }), span({ id: 2, chapter_position: 3 })], { compact: true });

    fireEvent.click(screen.getByRole("button", { name: /Wykryj fragmenty/ }));

    await waitFor(() => expect(props.onSpansChange).toHaveBeenCalled());
    expect(mocked.post.mock.calls[0][1]).toEqual({ whole_document: true });
    expect(props.onSpansChange.mock.calls[0][0].map((s: ToneSpan) => s.id)).toEqual([9]);
  });

  it("saves the reviewer's decision on a passage", async () => {
    mocked.patch.mockResolvedValue({ data: { span: span({ id: 1, status: "rejected" }) } });
    const props = renderPanel([span({ id: 1 }), span({ id: 2, quote: "Drugi fragment złośliwy tutaj." })]);

    fireEvent.click(screen.getAllByRole("button", { name: "✗ Odrzuć" })[0]);

    await waitFor(() => expect(props.onSpansChange).toHaveBeenCalled());
    expect(mocked.patch).toHaveBeenCalledWith("http://api/tone_spans/1", { status: "rejected" }, expect.anything());
    expect(props.onSpansChange.mock.calls[0][0].map((s: ToneSpan) => s.status)).toEqual(["rejected", "proposed"]);
  });

  it("offers the tone without outliers only when there are outliers, and asks the tone panel to reload", async () => {
    mocked.post.mockResolvedValue({ data: { model: "m", core_tone: { emotion: "neutralny" }, report: {} } });
    const props = renderPanel([span({ id: 1 })]);

    fireEvent.click(screen.getByRole("button", { name: /Ton bez fragmentów odstających/ }));

    await waitFor(() => expect(props.onToneChanged).toHaveBeenCalled());
    expect(mocked.post.mock.calls[0][0]).toBe("http://api/document/5/chapter/2/core_tone");
    expect(screen.getByRole("status").textContent).toContain("neutralny");
  });

  it("does not offer it without outlier passages, nor for a rejected one", () => {
    renderPanel([span({ role: "key", label: "kluczowy" }), span({ id: 2, status: "rejected" })]);

    expect(screen.queryByRole("button", { name: /Ton bez fragmentów odstających/ })).toBeNull();
  });

  it("shows the backend's own explanation when the tone cannot be recomputed", async () => {
    mocked.post.mockRejectedValue({
      message: "Request failed", response: { status: 409, data: { message: "Ten rozdział nie ma jeszcze oceny tonu." } },
      config: { method: "post", url: "http://api/x" },
    });
    renderPanel([span({ id: 1 })]);

    fireEvent.click(screen.getByRole("button", { name: /Ton bez fragmentów odstających/ }));

    expect((await screen.findByRole("alert")).textContent).toContain("Ten rozdział nie ma jeszcze oceny tonu.");
  });

  it("switches highlighting in the text on and off", () => {
    const props = renderPanel([]);

    fireEvent.click(screen.getByLabelText(/Podświetlaj w tekście/));

    expect(props.onHighlightChange).toHaveBeenCalledWith(false);
  });
});
