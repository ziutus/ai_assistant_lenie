import { describe, expect, it } from "vitest";
import { splitByEntities, type HighlightEntry } from "./entityHighlight";

const person: HighlightEntry = { kind: "persName", label: "Donald Tusk", variants: ["Donald Tusk", "Tuska"] };
const place: HighlightEntry = { kind: "place", label: "Kijów", variants: ["Kijów", "Kijowa"] };

describe("splitByEntities", () => {
  it("returns the sentence untouched without entries or matches", () => {
    expect(splitByEntities("Zwykłe zdanie.", [])).toEqual([{ text: "Zwykłe zdanie." }]);
    expect(splitByEntities("Zwykłe zdanie.", [person])).toEqual([{ text: "Zwykłe zdanie." }]);
  });

  it("splits around inflected surface forms and keeps the text lossless", () => {
    const text = "Rozmowa Tuska z mieszkańcami Kijowa trwała długo.";
    const segments = splitByEntities(text, [person, place]);
    expect(segments.map(segment => segment.text).join("")).toBe(text);
    expect(segments.filter(segment => segment.kind).map(segment => [segment.text, segment.kind, segment.label])).toEqual([
      ["Tuska", "persName", "Donald Tusk"],
      ["Kijowa", "place", "Kijów"],
    ]);
  });

  it("prefers the longest surface form", () => {
    const segments = splitByEntities("Donald Tusk wrócił.", [
      { kind: "persName", label: "Tusk", variants: ["Tusk"] }, person,
    ]);
    expect(segments[0]).toEqual({ text: "Donald Tusk", kind: "persName", label: "Donald Tusk" });
  });

  it("requires whole tokens, including Polish letters at the edges", () => {
    expect(splitByEntities("Kijówek to inna nazwa.", [place])).toEqual([{ text: "Kijówek to inna nazwa." }]);
    expect(splitByEntities("(Kijów)", [place]).filter(segment => segment.kind)).toHaveLength(1);
  });

  it("matches case-insensitively but a capitalised form needs a capitalised mention", () => {
    const union: HighlightEntry = { kind: "orgName", label: "Unia", variants: ["Unia"] };
    expect(splitByEntities("unia europejska", [union])).toEqual([{ text: "unia europejska" }]);
    expect(splitByEntities("UNIA europejska", [union]).filter(segment => segment.kind)).toHaveLength(1);
  });

  it("escapes regular-expression characters in names", () => {
    const company: HighlightEntry = { kind: "orgName", label: "A+B (SA)", variants: ["A+B (SA)"] };
    expect(splitByEntities("Spółka A+B (SA) ogłosiła.", [company]).filter(segment => segment.kind)).toHaveLength(1);
  });
});
