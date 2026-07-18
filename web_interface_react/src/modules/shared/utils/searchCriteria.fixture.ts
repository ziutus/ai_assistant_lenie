import type { SearchInterpretation } from "../hooks/useSearch";

export const criteriaFixture = (): SearchInterpretation => ({
  query: "gospodarka", author_name: null, publisher_name: "Onet", publisher_domain: null,
  discovery_source_name: null, collection_name: null, published_on_from: null,
  published_on_to: null, ingested_at_from: null, ingested_at_to: null,
  subject_period_start_year: 2004, subject_period_end_year: null,
  temporal_expression: "po wejściu do UE", document_types: ["webpage"], languages: ["pl"],
  sort: "published_desc", interpretation_summary: "Gospodarka po 2004", warnings: [],
  clarification_required: false, clarification_question: null, model_confidence: "high",
});
