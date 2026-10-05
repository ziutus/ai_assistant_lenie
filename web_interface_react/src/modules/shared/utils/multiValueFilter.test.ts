import { describe, expect, it } from "vitest";
import { filterCsv, filterValues } from "./multiValueFilter";

describe("string multi-value filters", () => {
  it("handles CSV, empty elements, duplicates, ALL and empty selections", () => {
    expect(filterValues(" a,,b,a, ", ["a", "b"])).toEqual(["a", "b"]);
    expect(filterValues("ALL", ["a", "b"])).toEqual(["a", "b"]);
    expect(filterValues("", ["a", "b"])).toEqual([]);
    expect(filterCsv(["b", "a"], ["a", "b"])).toBe("ALL");
    expect(filterCsv(["a", "b"], ["a", "b", "c"])).toBe("a,b");
    expect(filterCsv([], [])).toBe("");
  });
});
