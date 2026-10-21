import { describe, expect, it } from "vitest";
import { describeModel, modelOptionText } from "./modelDetails";

describe("describeModel", () => {
  it("formats price and limits of a priced model", () => {
    const text = describeModel({
      id: "openrouter/openai/gpt-4o-mini", label: "GPT-4o mini", input_price_per_million: "0.15",
      output_price_per_million: "0.6", currency: "USD", context_length: 128000, max_output_tokens: 16384,
    });
    expect(text).toBe("$0.15 / $0.6 za 1 mln tok. · okno 128 tys. · wyjście do 16 tys.");
  });

  it("shows a million-token window compactly", () => {
    expect(describeModel({ id: "a", label: "A", context_length: 1048576 })).toBe("okno 1 mln");
  });

  it("stays silent when nothing is known", () => {
    expect(describeModel({ id: "b", label: "B" })).toBe("");
    expect(modelOptionText({ id: "b", label: "B" })).toBe("B");
  });

  it("flags a model the provider catalog no longer lists", () => {
    expect(describeModel({ id: "c", label: "C", listed_by_provider: false })).toBe("brak w katalogu dostawcy");
  });

  it("appends details to the label", () => {
    expect(modelOptionText({ id: "d", label: "Bielik", input_price_per_million: "0.56", output_price_per_million: "0.56", currency: "EUR" }))
      .toBe("Bielik — €0.56 / €0.56 za 1 mln tok.");
  });
});
