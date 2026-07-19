import React from "react";
import { useFormik } from "formik";
import { useSearchParams } from "react-router-dom";
import ListItemSearchSimilar from "../../../utils";
import Input from "../components/Input/input";
import Select from "../components/Select/select";
import { SearchInterpretationPanel } from "../components/SearchInterpretationPanel";
import { SearchCriteriaEditor } from "../components/SearchCriteriaEditor";
import { type SearchInterpretation, useSearch } from "../hooks/useSearch";
import { explicitSearchParams, parseExplicitCriteria } from "../utils/searchCriteria";

const ALLOWED_LIMITS = ["5", "10", "30", "50"];
const DEFAULT_LIMIT = "10";

const Search = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const limitParam = searchParams.get("limit") ?? DEFAULT_LIMIT;
  const initialLimit = ALLOWED_LIMITS.includes(limitParam) ? limitParam : DEFAULT_LIMIT;
  const initialExplicitCriteria = searchParams.get("mode") === "explicit"
    ? parseExplicitCriteria(searchParams.get("criteria")) : null;
  const [submittedQuery, setSubmittedQuery] = React.useState(initialQuery);
  const [draftCriteria, setDraftCriteria] = React.useState<SearchInterpretation | null>(initialExplicitCriteria);
  const {
    handleSearch, handleExplicitSearch, sendFeedback, clearSearch,
    results, searchResponse, originSearchId, feedbackMessage, isLoading, message, isError,
  } = useSearch();

  React.useEffect(() => {
    if (searchResponse?.interpretation) setDraftCriteria(searchResponse.interpretation);
  }, [searchResponse]);

  const formik = useFormik({
    initialValues: { search: initialQuery, searchLimit: initialLimit },
    onSubmit: async data => {
      const query = data.search.trim();
      setSubmittedQuery(query);
      const params: Record<string, string> = { q: query };
      if (data.searchLimit !== DEFAULT_LIMIT) params.limit = data.searchLimit;
      setSearchParams(params);
      await handleSearch(query, data.searchLimit);
    },
  });

  const initialSearchDone = React.useRef(false);
  React.useEffect(() => {
    if (!initialSearchDone.current && initialExplicitCriteria) {
      initialSearchDone.current = true;
      void handleExplicitSearch(initialExplicitCriteria, initialLimit);
    } else if (!initialSearchDone.current && initialQuery) {
      initialSearchDone.current = true;
      void handleSearch(initialQuery, initialLimit);
    }
  }, [handleExplicitSearch, handleSearch, initialExplicitCriteria, initialQuery, initialLimit]);

  const handleClean = () => {
    formik.resetForm({ values: { search: "", searchLimit: DEFAULT_LIMIT } });
    clearSearch();
    setSubmittedQuery("");
    setDraftCriteria(null);
    setSearchParams({});
  };

  const applyCorrection = async () => {
    if (!draftCriteria) return;
    setSubmittedQuery(draftCriteria.query ?? "");
    const searched = await handleExplicitSearch(draftCriteria, formik.values.searchLimit);
    if (searched) {
      setSearchParams(explicitSearchParams(draftCriteria, formik.values.searchLimit));
      if (originSearchId != null) await sendFeedback("partially_correct", draftCriteria);
    }
  };

  return (
    <form onSubmit={formik.handleSubmit}>
      <h2 style={{ marginBottom: 4 }}>Wyszukiwanie</h2>
      <p style={{ marginTop: 0, color: "#64748b", fontSize: ".88rem" }}>
        Opisz zwykłym zdaniem, czego szukasz. Bielik wydzieli temat i filtry.
      </p>
      <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <div style={{ minWidth: "min(520px, 100%)", flex: "1 1 420px" }}>
          <Input required disabled={isLoading} value={formik.values.search}
            label="Czego szukasz?" onChange={formik.handleChange}
            id="search" name="search" type="text" />
        </div>
        <Select disabled={isLoading} value={formik.values.searchLimit} label="Liczba wyników"
          onChange={formik.handleChange} id="searchLimit" name="searchLimit" type="text">
          {ALLOWED_LIMITS.map(limit => <option key={limit} value={limit}>{limit}</option>)}
        </Select>
        <button type="submit" style={{ marginTop: 11 }} className="button" disabled={isLoading}>Szukaj</button>
        <button type="button" className="button" style={{ marginTop: 11 }} onClick={handleClean}>Wyczyść</button>
      </div>

      {isLoading && <div className="loader" />}
      {isError && <p className="errorText">{message}</p>}
      {searchResponse && !isLoading && (
        <SearchInterpretationPanel interpretation={searchResponse.interpretation}
          fallbackUsed={searchResponse.fallback_used} />
      )}
      {draftCriteria && !isLoading && (
        <SearchCriteriaEditor criteria={draftCriteria} disabled={isLoading}
          onChange={setDraftCriteria} onApply={() => { void applyCorrection(); }} />
      )}
      {originSearchId != null && !isLoading && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 14 }}>
          <span style={{ color: "#475569", fontSize: ".84rem" }}>Czy interpretacja była poprawna?</span>
          <button type="button" className="button" onClick={() => { void sendFeedback("correct"); }}>Tak</button>
          <button type="button" className="button" onClick={() => { void sendFeedback("incorrect"); }}>Nie</button>
          {feedbackMessage && <span role="status" style={{ fontSize: ".82rem" }}>{feedbackMessage}</span>}
        </div>
      )}
      {results && !isLoading && (
        <div style={{ margin: "18px 0 10px", color: "#64748b", fontSize: ".85rem" }}>
          Znaleziono: <strong style={{ color: "#334155" }}>{results.length}</strong>
        </div>
      )}
      <div style={{ display: "grid", gap: 12, maxWidth: 1050, paddingBottom: 30 }}>
        {results?.map(item => (
          <ListItemSearchSimilar key={`${item.document_id}-${item.chunk_id ?? item.id ?? "text"}`}
            item={item} query={searchResponse?.interpretation.query ?? submittedQuery} />
        ))}
      </div>
    </form>
  );
};

export default Search;
