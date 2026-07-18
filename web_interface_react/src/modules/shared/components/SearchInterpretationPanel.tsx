import React from "react";
import type { SearchInterpretation } from "../hooks/useSearch";

const FILTER_LABELS: Partial<Record<keyof SearchInterpretation, string>> = {
  author_name: "Autor",
  publisher_name: "Wydawca",
  publisher_domain: "Domena wydawcy",
  discovery_source_name: "Źródło odkrycia",
  collection_name: "Kolekcja",
  published_on_from: "Publikacja od",
  published_on_to: "Publikacja do",
  ingested_at_from: "Dodano od",
  ingested_at_to: "Dodano do",
  subject_period_start_year: "Okres treści od",
  subject_period_end_year: "Okres treści do",
  temporal_expression: "Wyrażenie czasowe",
  document_types: "Typy dokumentów",
  languages: "Języki",
  sort: "Sortowanie",
};

const displayValue = (value: unknown) => Array.isArray(value) ? value.join(", ") : String(value);

const activeFilters = (interpretation: SearchInterpretation) =>
  Object.entries(FILTER_LABELS).flatMap(([key, label]) => {
    const value = interpretation[key as keyof SearchInterpretation];
    if (value == null || value === "" || (Array.isArray(value) && value.length === 0)) return [];
    if (key === "sort" && value === "relevance") return [];
    return [{ key, label: label as string, value: displayValue(value) }];
  });

export const SearchInterpretationPanel = ({
  interpretation,
  fallbackUsed,
}: {
  interpretation: SearchInterpretation;
  fallbackUsed: boolean;
}) => {
  const filters = activeFilters(interpretation);
  const warnings = interpretation.warnings ?? [];
  return (
    <section aria-label="Interpretacja zapytania" style={{
      margin: "18px 0", padding: "16px 18px", border: "1px solid #bfdbfe",
      borderRadius: 10, background: "#eff6ff", maxWidth: 1050,
    }}>
      <h3 style={{ margin: "0 0 8px", color: "#1e3a8a" }}>Bielik zinterpretował zapytanie jako</h3>
      <p style={{ margin: "0 0 10px", color: "#334155" }}>{interpretation.interpretation_summary}</p>
      {interpretation.query && <div><strong>Temat:</strong> {interpretation.query}</div>}
      {filters.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 10 }}>
          {filters.map(filter => (
            <span key={filter.key} style={{
              borderRadius: 999, padding: "4px 9px", background: "#dbeafe",
              color: "#1e3a8a", fontSize: ".82rem",
            }}><strong>{filter.label}:</strong> {filter.value}</span>
          ))}
        </div>
      )}
      {fallbackUsed && (
        <p role="alert" style={{ margin: "12px 0 0", color: "#9a3412", fontWeight: 600 }}>
          Nie udało się użyć interpretacji Bielika — wyszukano dosłowną frazę.
        </p>
      )}
      {warnings.length > 0 && (
        <ul style={{ margin: "12px 0 0", color: "#92400e" }}>
          {warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}
        </ul>
      )}
      {interpretation.clarification_required && interpretation.clarification_question && (
        <p role="alert" style={{ margin: "12px 0 0", fontWeight: 600 }}>
          {interpretation.clarification_question}
        </p>
      )}
    </section>
  );
};
