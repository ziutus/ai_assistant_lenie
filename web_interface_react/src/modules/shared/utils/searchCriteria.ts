import type { SearchInterpretation } from "../hooks/useSearch";

export const SEARCH_FILTER_KEYS = [
  "author_name", "publisher_name", "publisher_domain", "discovery_source_name",
  "collection_name", "published_on_from", "published_on_to", "ingested_at_from",
  "ingested_at_to", "subject_period_start_year", "subject_period_end_year",
  "document_types", "languages",
] as const;

export type SearchFilterKey = typeof SEARCH_FILTER_KEYS[number];

export const emptySearchCriteria = (query = ""): SearchInterpretation => ({
  query: query || null, author_name: null, publisher_name: null, publisher_domain: null,
  discovery_source_name: null, collection_name: null, published_on_from: null,
  published_on_to: null, ingested_at_from: null, ingested_at_to: null,
  subject_period_start_year: null, subject_period_end_year: null, temporal_expression: null,
  document_types: [], languages: [], sort: "relevance",
  interpretation_summary: "Jawne kryteria wyszukiwania (bez interpretacji LLM).", warnings: [],
  clarification_required: false, clarification_question: null, model_confidence: "high",
});

export const buildExplicitSearchPayload = (criteria: SearchInterpretation, limit: string) => {
  const filters = Object.fromEntries(SEARCH_FILTER_KEYS.flatMap(key => {
    const value = criteria[key];
    return value == null || value === "" || (Array.isArray(value) && value.length === 0)
      ? [] : [[key, value]];
  }));
  return {
    ...(criteria.query ? { query: criteria.query } : {}),
    filters,
    limit: Number(limit),
    sort: criteria.sort,
  };
};

export const explicitSearchParams = (criteria: SearchInterpretation, limit: string) => ({
  mode: "explicit",
  criteria: JSON.stringify(criteria),
  ...(limit === "10" ? {} : { limit }),
});

export const parseExplicitCriteria = (raw: string | null): SearchInterpretation | null => {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && typeof parsed.interpretation_summary === "string"
      ? parsed as SearchInterpretation : null;
  } catch {
    return null;
  }
};
