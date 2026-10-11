import { describe, expect, it } from "vitest";
import { ageLabel, difficultyLabel, reviewLabel } from "./projectCards";

describe("project card labels", () => {
  it("formats age ranges", () => {
    expect(ageLabel(5, 9)).toBe("5–9");
    expect(ageLabel(7, null)).toBe("7+");
    expect(ageLabel(6, 6)).toBe("6+");
    expect(ageLabel(null, null)).toBe("—");
  });

  it("labels difficulty and review status", () => {
    expect(difficultyLabel(1)).toBe("Łatwy");
    expect(difficultyLabel(2)).toBe("Średni");
    expect(difficultyLabel(null)).toBe("—");
    expect(reviewLabel.reviewed).toBe("sprawdzona");
  });
});
