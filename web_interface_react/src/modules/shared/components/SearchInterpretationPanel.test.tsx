import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SearchInterpretationPanel } from "./SearchInterpretationPanel";
import type { SearchInterpretation } from "../hooks/useSearch";

const interpretation = (overrides: Partial<SearchInterpretation> = {}): SearchInterpretation => ({
  query: "gospodarka Polski",
  author_name: null,
  publisher_name: "Onet.pl",
  publisher_domain: "onet.pl",
  discovery_source_name: null,
  collection_name: null,
  published_on_from: null,
  published_on_to: null,
  ingested_at_from: null,
  ingested_at_to: null,
  subject_period_start_year: 2004,
  subject_period_end_year: null,
  temporal_expression: "po wejściu do UE",
  document_types: ["webpage"],
  languages: ["pl"],
  sort: "relevance",
  interpretation_summary: "Gospodarka Polski po wejściu do UE",
  warnings: [],
  clarification_required: false,
  clarification_question: null,
  model_confidence: "high",
  ...overrides,
});

describe("SearchInterpretationPanel", () => {
  it("shows the interpreted query and every active filter", () => {
    render(<SearchInterpretationPanel interpretation={interpretation()} fallbackUsed={false} />);
    expect(screen.getByRole("heading", { name: "Bielik zinterpretował zapytanie jako" })).toBeTruthy();
    expect(screen.getByText(/Temat:/).parentElement?.textContent).toContain("gospodarka Polski");
    expect(screen.getByText(/Wydawca:/).closest("span")?.textContent).toContain("Onet.pl");
    expect(screen.getByText(/Okres treści od:/).closest("span")?.textContent).toContain("2004");
    expect(screen.getByText(/Typy dokumentów:/).closest("span")?.textContent).toContain("webpage");
    expect(screen.getByText(/Języki:/).closest("span")?.textContent).toContain("pl");
    expect(screen.queryByText(/Sortowanie:/)).toBeNull();
  });

  it("makes fallback and warnings visible", () => {
    render(<SearchInterpretationPanel interpretation={interpretation({
      warnings: ["Nie podano końca okresu."],
    })} fallbackUsed />);
    expect(screen.getByRole("alert").textContent).toContain("dosłowną frazę");
    expect(screen.getByText("Nie podano końca okresu.")).toBeTruthy();
  });

  it("shows a clarification question", () => {
    render(<SearchInterpretationPanel interpretation={interpretation({
      clarification_required: true,
      clarification_question: "Którego autora masz na myśli?",
    })} fallbackUsed={false} />);
    expect(screen.getByRole("alert").textContent).toBe("Którego autora masz na myśli?");
  });
});
