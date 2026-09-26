import { describe, expect, it } from "vitest";
import { parsePartialDateInput, partialDateToDisplay } from "./partialDate";

describe("parsePartialDateInput", () => {
  it.each([
    ["", null],
    ["  ", null],
    ["2016", "2016"],
    ["03.2015", "2015-03"],
    ["3.2015", "2015-03"],
    ["03-2015", "2015-03"],
    ["03/2015", "2015-03"],
    ["2015-03", "2015-03"],
    ["01.03.2015", "2015-03-01"],
    ["5.3.2015", "2015-03-05"],
    ["2015-03-05", "2015-03-05"],
    ["29.02.2024", "2024-02-29"],
  ])("%j -> %j", (text, expected) => {
    expect(parsePartialDateInput(text)).toBe(expected);
  });

  it.each(["16", "13.2015", "00.2015", "31.02.2015", "2015-13", "0999", "abc", "1.2.3", "2015-03-5x"])(
    "%j is not a date", (text) => {
      expect(parsePartialDateInput(text)).toBeUndefined();
    });
});

describe("partialDateToDisplay", () => {
  it.each([
    ["2016", "2016"],
    ["2015-03", "03.2015"],
    ["2015-03-05", "05.03.2015"],
    [null, ""],
    [undefined, ""],
  ])("%j -> %j", (value, expected) => {
    expect(partialDateToDisplay(value)).toBe(expected);
  });

  it("round-trips through the parser", () => {
    for (const wire of ["2016", "2015-03", "2015-03-05"]) {
      expect(parsePartialDateInput(partialDateToDisplay(wire))).toBe(wire);
    }
  });
});
