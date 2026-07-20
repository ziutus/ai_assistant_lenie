import React from "react";
import axios from "axios";
import type { SearchInterpretation } from "../hooks/useSearch";
import { AuthorizationContext } from "../context/authorizationContext";
import { DOCUMENT_TYPE_OPTIONS, SEARCH_FILTER_KEYS, type SearchFilterKey } from "../utils/searchCriteria";

const LABELS: Record<SearchFilterKey, string> = {
  author_name: "Autor", publisher_name: "Wydawca", publisher_domain: "Domena wydawcy",
  discovery_source_name: "Źródło odkrycia", collection_name: "Kolekcja",
  published_on_from: "Publikacja od", published_on_to: "Publikacja do",
  ingested_at_from: "Dodano od", ingested_at_to: "Dodano do",
  subject_period_start_year: "Okres od", subject_period_end_year: "Okres do",
  document_types: "Typy", languages: "Języki",
};

const present = (value: unknown) => value != null && value !== ""
  && (!Array.isArray(value) || value.length > 0);

const inputValue = (value: unknown) => Array.isArray(value) ? value.join(", ") : String(value ?? "");

const CheckboxGroup = ({ label, options, selected, disabled, onToggle }: {
  label: string;
  options: { value: string; label: string }[];
  selected: Set<string>;
  disabled: boolean;
  onToggle: (value: string) => void;
}) => (
  <fieldset style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: "5px 7px", background: "#fff" }}>
    <legend style={{ fontSize: ".78rem", color: "#475569", padding: "0 4px" }}>{label}</legend>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {options.map(option => (
        <label key={option.value} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: ".82rem" }}>
          <input type="checkbox" disabled={disabled} checked={selected.has(option.value)}
            onChange={() => onToggle(option.value)} />
          {option.label}
        </label>
      ))}
    </div>
  </fieldset>
);

export const SearchCriteriaEditor = ({
  criteria, disabled, onChange, onApply,
  title = "Popraw interpretację", applyLabel = "Szukaj z poprawionymi kryteriami",
}: {
  criteria: SearchInterpretation;
  disabled: boolean;
  onChange: (criteria: SearchInterpretation) => void;
  onApply: () => void;
  title?: string;
  applyLabel?: string;
}) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [languageOptions, setLanguageOptions] = React.useState<
    { code: string; name_pl: string; count: number }[]
  >([]);

  React.useEffect(() => {
    axios.get(`${apiUrl}/languages`, { headers: { "x-api-key": `${apiKey}` } })
      .then(response => setLanguageOptions(response.data.languages ?? []))
      .catch(() => undefined);
  }, [apiUrl, apiKey]);

  // document_types is always checkboxes; languages is checkboxes once GET /languages has
  // answered, and falls back to the comma-separated text field below otherwise (so typing a
  // code the picker doesn't know about yet still works — the backend filter itself stays a
  // permissive regex, not an enum, see library/search/types.py). Neither goes through
  // update()/remove() when rendered as checkboxes.
  const update = (key: SearchFilterKey, raw: string) => {
    let value: string | number | string[] | null = raw;
    if (key === "languages") {
      value = raw.split(",").map(item => item.trim()).filter(Boolean);
    } else if (key === "subject_period_start_year" || key === "subject_period_end_year") {
      value = raw === "" ? null : Number(raw);
    }
    onChange({ ...criteria, [key]: value });
  };
  const remove = (key: SearchFilterKey) => onChange({ ...criteria, [key]: key === "languages" ? [] : null });
  const toggleArrayValue = (key: "document_types" | "languages", value: string) => onChange({
    ...criteria,
    [key]: criteria[key].includes(value)
      ? criteria[key].filter(v => v !== value)
      : [...criteria[key], value],
  });

  return (
    <section aria-label={title} style={{ margin: "12px 0 18px", maxWidth: 1050 }}>
      <h4 style={{ marginBottom: 8 }}>{title}</h4>
      <label style={{ display: "block", marginBottom: 8 }}>
        Temat
        <input aria-label="Temat" disabled={disabled} value={criteria.query ?? ""}
          onChange={event => onChange({ ...criteria, query: event.target.value || null })}
          style={{ display: "block", width: "min(600px, 100%)" }} />
      </label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {SEARCH_FILTER_KEYS.map(key => {
          if (key === "document_types") {
            return (
              <CheckboxGroup key={key} label={LABELS[key]} disabled={disabled}
                options={DOCUMENT_TYPE_OPTIONS} selected={new Set(criteria.document_types)}
                onToggle={value => toggleArrayValue("document_types", value)} />
            );
          }
          if (key === "languages" && languageOptions.length > 0) {
            return (
              <CheckboxGroup key={key} label={LABELS[key]} disabled={disabled}
                options={languageOptions.map(option => ({
                  value: option.code, label: `${option.name_pl} (${option.code}) · ${option.count}`,
                }))}
                selected={new Set(criteria.languages)}
                onToggle={value => toggleArrayValue("languages", value)} />
            );
          }
          return (
            <label key={key} style={{ display: "flex", alignItems: "center", gap: 5,
              border: "1px solid #cbd5e1", borderRadius: 8, padding: "5px 7px", background: "#fff" }}>
              <span style={{ fontSize: ".78rem", color: "#475569" }}>{LABELS[key]}</span>
              <input aria-label={LABELS[key]} disabled={disabled} value={inputValue(criteria[key])}
                type={key === "published_on_from" || key === "published_on_to"
                  || key === "ingested_at_from" || key === "ingested_at_to" ? "date"
                  : key.startsWith("subject_period_") ? "number" : "text"}
                onChange={event => update(key, event.target.value)} style={{ width: 130 }} />
              {present(criteria[key]) && (
                <button aria-label={`Usuń filtr ${LABELS[key]}`} type="button" disabled={disabled}
                  onClick={() => remove(key)} style={{ border: 0, background: "transparent", cursor: "pointer" }}>×</button>
              )}
            </label>
          );
        })}
      </div>
      <button type="button" className="button" disabled={disabled || (!criteria.query &&
        SEARCH_FILTER_KEYS.every(key => !present(criteria[key])))} onClick={onApply} style={{ marginTop: 10 }}>
        {applyLabel}
      </button>
    </section>
  );
};
