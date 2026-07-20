import { describe, expect, it } from "vitest";
import {
  buildExplicitSearchPayload, emptySearchCriteria, explicitSearchParams, parseExplicitCriteria,
} from "./searchCriteria";
import { criteriaFixture } from "./searchCriteria.fixture";

describe("explicit search criteria", () => {
  it("builds an explicit backend request without natural_query or UI metadata", () => {
    const payload = buildExplicitSearchPayload(criteriaFixture(), "30") as Record<string, any>;
    expect(payload.query).toBe("gospodarka");
    expect(payload.filters).toEqual({
      publisher_name: "Onet", subject_period_start_year: 2004,
      document_types: ["webpage"], languages: ["pl"],
    });
    expect(payload.limit).toBe(30);
    expect(payload.sort).toBe("published_desc");
    expect(payload.natural_query).toBeUndefined();
    expect(payload.filters.temporal_expression).toBeUndefined();
  });

  it("round-trips shareable explicit URL criteria", () => {
    const criteria = criteriaFixture();
    const params = explicitSearchParams(criteria, "10");
    expect(params.mode).toBe("explicit");
    expect(parseExplicitCriteria(params.criteria)).toEqual(criteria);
    expect(parseExplicitCriteria("not-json")).toBeNull();
  });
});

describe("emptySearchCriteria", () => {
  it("produces a criteria object with every filter unset and no query", () => {
    const criteria = emptySearchCriteria();
    expect(criteria.query).toBeNull();
    expect(criteria.document_types).toEqual([]);
    expect(criteria.languages).toEqual([]);
    expect(criteria.subject_period_start_year).toBeNull();
    const payload = buildExplicitSearchPayload(criteria, "10") as Record<string, any>;
    expect(payload.query).toBeUndefined();
    expect(payload.filters).toEqual({});
  });

  it("prefills the topic when given a query", () => {
    expect(emptySearchCriteria("gospodarka").query).toBe("gospodarka");
  });
});
