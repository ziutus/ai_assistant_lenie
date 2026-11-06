import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import type { AuthorizationState } from "../../../../types";
import { AuthorizationContext } from "../../context/authorizationContext";
import TonePanel from "../TonePanel/tonePanel";
import TimePeriodsPanel from "../TimePeriodsPanel/timePeriodsPanel";
import ChapterAnalysisRunner, { describeRun } from "./chapterAnalysisRunner";

vi.mock("axios");
const mocked = vi.mocked(axios, true);

afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals(); });

const MODELS = {
  default_model: "Bielik-11B-v3.0-Instruct",
  saved: false,
  models: [
    { id: "Bielik-11B-v3.0-Instruct", label: "Bielik 11B v3", input_price_per_million: "0.56", output_price_per_million: "0.56", currency: "EUR", context_length: 32000 },
    { id: "openrouter/mistralai/mistral-small-3.2-24b-instruct", label: "Mistral Small 3.2", external: true, input_price_per_million: "0.1", output_price_per_million: "0.3", currency: "USD", context_length: 128000 },
  ],
};

const auth: AuthorizationState = {
  apiUrl: "http://api", apiKey: "k", apiType: "Docker",
  setApiUrl: vi.fn(), setApiKey: vi.fn(), setApiType: vi.fn(),
  searchInDocument: "", setSearchInDocument: vi.fn(), searchType: "strict", setSearchType: vi.fn(),
  selectedDocumentType: "link", setSelectedDocumentType: vi.fn(),
  selectedDocumentState: "NEED_MANUAL_REVIEW", setSelectedDocumentState: vi.fn(),
};

const openPicker = () => {
  const summary = screen.getByText(/^Model: /);
  const details = summary.closest("details") as HTMLDetailsElement;
  details.open = true;
  fireEvent(details, new Event("toggle"));
};

describe("ChapterAnalysisRunner", () => {
  it("loads the models only when the picker is opened and shows price and window next to each", async () => {
    mocked.get.mockResolvedValue({ data: MODELS });
    render(
      <ChapterAnalysisRunner apiUrl="http://api" apiKey="k" docId={5} position={2} endpoint="detect_tone"
        resultKey="tones" summary="Ocena tonu" buttonLabel="Oceń" title="t" onResult={vi.fn()} />,
    );
    expect(mocked.get).not.toHaveBeenCalled();

    openPicker();

    const option = await screen.findByRole("option", { name: /Mistral Small 3.2/ });
    expect(option.textContent).toContain("okno 128 tys.");
    expect(option.textContent).toContain("$0.1 / $0.3 za 1 mln tok.");
    expect(screen.getByRole("option", { name: /Bielik 11B v3/ }).textContent).toContain("— domyślny");
    expect(mocked.get).toHaveBeenCalledWith("http://api/chapter_analysis/model", expect.anything());
  });

  it("warns that an external model receives the chapter text", async () => {
    mocked.get.mockResolvedValue({ data: MODELS });
    render(
      <ChapterAnalysisRunner apiUrl="http://api" apiKey="k" docId={5} position={2} endpoint="detect_tone"
        resultKey="tones" summary="Ocena tonu" buttonLabel="Oceń" title="t" onResult={vi.fn()} />,
    );
    openPicker();
    await screen.findByRole("option", { name: /Mistral Small 3.2/ });

    fireEvent.change(screen.getByLabelText("Model do analizy rozdziału"), {
      target: { value: "openrouter/mistralai/mistral-small-3.2-24b-instruct" },
    });

    expect(screen.getByText(/Zewnętrzny dostawca/)).toBeTruthy();
  });

  it("runs one chapter with the chosen model and reports the cost and the fragments", async () => {
    mocked.get.mockResolvedValue({ data: MODELS });
    mocked.post.mockResolvedValue({
      data: {
        model: "openrouter/mistralai/mistral-small-3.2-24b-instruct", kept_previous: false,
        tones: [{ chapter_position: 2, emotion: "smutny" }],
        report: { fragments: 3, fragments_skipped: 0, llm_cost_amount: "0.0123", llm_cost_currency: "USD" },
      },
    });
    const onResult = vi.fn();
    render(
      <ChapterAnalysisRunner apiUrl="http://api" apiKey="k" docId={5} position={2} endpoint="detect_tone"
        resultKey="tones" summary="Ocena tonu" buttonLabel="Oceń" title="t" onResult={onResult} />,
    );
    openPicker();
    await screen.findByRole("option", { name: /Mistral Small 3.2/ });
    fireEvent.change(screen.getByLabelText("Model do analizy rozdziału"), {
      target: { value: "openrouter/mistralai/mistral-small-3.2-24b-instruct" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Oceń" }));

    await waitFor(() => expect(onResult).toHaveBeenCalled());
    expect(mocked.post.mock.calls[0][0]).toBe("http://api/document/5/chapter/2/detect_tone");
    expect(mocked.post.mock.calls[0][1]).toEqual({ model: "openrouter/mistralai/mistral-small-3.2-24b-instruct" });
    expect(onResult.mock.calls[0][0].items).toEqual([{ chapter_position: 2, emotion: "smutny" }]);
    const status = screen.getByRole("status").textContent ?? "";
    expect(status).toContain("w 3 fragmentach");
    expect(status).toContain("koszt 0.0123 USD");
  });

  it("sends no model when the picker was never opened, so the server default applies", async () => {
    mocked.post.mockResolvedValue({ data: { model: "m", kept_previous: false, time_periods: [], report: {} } });
    render(
      <ChapterAnalysisRunner apiUrl="http://api" apiKey="k" docId={5} position={4} endpoint="detect_time_period"
        resultKey="time_periods" summary="Ocena okresu" buttonLabel="Oceń okres" title="t" onResult={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Oceń okres" }));

    await waitFor(() => expect(mocked.post).toHaveBeenCalled());
    expect(mocked.post.mock.calls[0][0]).toBe("http://api/document/5/chapter/4/detect_time_period");
    expect(mocked.post.mock.calls[0][1]).toEqual({});
  });

  it("explains a failed request in plain Polish with technical details", async () => {
    mocked.post.mockRejectedValue({ message: "Network Error", code: "ERR_NETWORK", config: { method: "post", url: "http://api/x" } });
    render(
      <ChapterAnalysisRunner apiUrl="http://api" apiKey="k" docId={5} position={2} endpoint="detect_tone"
        resultKey="tones" summary="Ocena tonu" buttonLabel="Oceń" title="t" onResult={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Oceń" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Ocena tonu (rozdział 2)");
    expect(screen.getByText("Szczegóły techniczne")).toBeTruthy();
  });

  it("saves the household default and offers to restore the built-in one", async () => {
    mocked.get.mockResolvedValue({ data: MODELS });
    mocked.put.mockResolvedValue({
      data: { default_model: "openrouter/mistralai/mistral-small-3.2-24b-instruct", saved: true },
    });
    render(
      <ChapterAnalysisRunner apiUrl="http://api" apiKey="k" docId={5} position={2} endpoint="detect_tone"
        resultKey="tones" summary="Ocena tonu" buttonLabel="Oceń" title="t" onResult={vi.fn()} />,
    );
    openPicker();
    await screen.findByRole("option", { name: /Mistral Small 3.2/ });
    fireEvent.change(screen.getByLabelText("Model do analizy rozdziału"), {
      target: { value: "openrouter/mistralai/mistral-small-3.2-24b-instruct" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Ustaw jako domyślny" }));

    expect(await screen.findByRole("button", { name: "Przywróć domyślny serwera" })).toBeTruthy();
    expect(mocked.put).toHaveBeenCalledWith(
      "http://api/chapter_analysis/model",
      { model: "openrouter/mistralai/mistral-small-3.2-24b-instruct" },
      expect.anything(),
    );
  });
});

describe("describeRun", () => {
  it("says the previous result was kept when the answer was unusable", () => {
    const text = describeRun({ model: "m", kept_previous: true, items: [], report: {} }, "poprzedni ton");
    expect(text).toContain("poprzedni ton bez zmian");
  });

  it("mentions fragments left out by the cost cap", () => {
    const text = describeRun({ model: "m", kept_previous: false, items: [], report: { fragments: 12, fragments_skipped: 4 } }, "x");
    expect(text).toContain("pominięto 4 fragm.");
  });
});

const fetchJson = (body: unknown) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }));

describe("panels", () => {
  it("TonePanel replaces the tone of the chapter after a new assessment", async () => {
    vi.stubGlobal("fetch", fetchJson({
      status: "success", enrichment_run_at: "2026-11-01T10:00:00",
      tones: [{ chapter_position: 2, emotion: "neutralny", secondary_emotions: null, sentiment: "neutralne", intensity: "niska", registers: null, evidence: null }],
    }));
    mocked.post.mockResolvedValue({
      data: {
        model: "m", kept_previous: false, report: { fragments: 2 },
        tones: [{ chapter_position: 2, emotion: "gniewny", secondary_emotions: null, sentiment: "negatywne", intensity: "wysoka", registers: null, evidence: null }],
      },
    });
    render(<AuthorizationContext.Provider value={auth}><TonePanel docId="5" currentChapter={2} /></AuthorizationContext.Provider>);
    expect(await screen.findByText("neutralny")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "🎭 Oceń ton rozdziału" }));

    expect(await screen.findByText("gniewny")).toBeTruthy();
    expect(screen.queryByText("neutralny")).toBeNull();
    expect(mocked.post.mock.calls[0][0]).toBe("http://api/document/5/chapter/2/detect_tone");
  });

  it("TonePanel keeps the stored tone when the model's answer was unusable", async () => {
    vi.stubGlobal("fetch", fetchJson({
      status: "success", enrichment_run_at: "2026-11-01T10:00:00",
      tones: [{ chapter_position: 2, emotion: "neutralny", secondary_emotions: null, sentiment: "neutralne", intensity: "niska", registers: null, evidence: null }],
    }));
    mocked.post.mockResolvedValue({ data: { model: "m", kept_previous: true, tones: [], report: { invalid_json: 1 } } });
    render(<AuthorizationContext.Provider value={auth}><TonePanel docId="5" currentChapter={2} /></AuthorizationContext.Provider>);
    await screen.findByText("neutralny");

    fireEvent.click(screen.getByRole("button", { name: "🎭 Oceń ton rozdziału" }));

    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("poprzedni ton bez zmian"));
    expect(screen.getByText("neutralny")).toBeTruthy();
  });

  it("TonePanel offers the assessment even for a document analysed before with no tone for this chapter", async () => {
    vi.stubGlobal("fetch", fetchJson({ status: "success", enrichment_run_at: "2026-11-01T10:00:00", tones: [] }));
    render(<AuthorizationContext.Provider value={auth}><TonePanel docId="5" currentChapter={3} /></AuthorizationContext.Provider>);

    expect(await screen.findByText(/Brak tonu dla tego rozdziału/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "🎭 Oceń ton rozdziału" })).toBeTruthy();
  });

  it("TimePeriodsPanel replaces only the periods of the assessed chapter", async () => {
    vi.stubGlobal("fetch", fetchJson({
      status: "success", enrichment_run_at: "2026-11-01T10:00:00",
      time_periods: [
        { chapter_position: 1, position: 0, subject_period_label: "starożytność", subject_period_start_year: null, subject_period_end_year: null, confidence: "high", evidence: null },
        { chapter_position: 2, position: 0, subject_period_label: "stary okres", subject_period_start_year: null, subject_period_end_year: null, confidence: "high", evidence: null },
      ],
    }));
    mocked.post.mockResolvedValue({
      data: {
        model: "m", kept_previous: false, report: {},
        time_periods: [{ chapter_position: 2, position: 0, subject_period_label: "nowy okres", subject_period_start_year: 1939, subject_period_end_year: 1945, confidence: "high", evidence: null }],
      },
    });
    render(<AuthorizationContext.Provider value={auth}><TimePeriodsPanel docId="5" currentChapter={2} /></AuthorizationContext.Provider>);
    await screen.findByText("stary okres");

    fireEvent.click(screen.getByRole("button", { name: "⏳ Oceń okres rozdziału" }));

    expect(await screen.findByText("nowy okres")).toBeTruthy();
    expect(screen.queryByText("stary okres")).toBeNull();
    expect(mocked.post.mock.calls[0][0]).toBe("http://api/document/5/chapter/2/detect_time_period");
  });
});
