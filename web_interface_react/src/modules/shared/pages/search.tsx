import React from "react";
import { useFormik } from "formik";
import { useSearchParams } from "react-router-dom";
import ListItemSearchSimilar from "../../../utils";
import Input from "../components/Input/input";
import Select from "../components/Select/select";
import { SearchInterpretationPanel } from "../components/SearchInterpretationPanel";
import { SearchCriteriaEditor } from "../components/SearchCriteriaEditor";
import { type SearchInterpretation, useSearch } from "../hooks/useSearch";
import { emptySearchCriteria, explicitSearchParams, parseExplicitCriteria } from "../utils/searchCriteria";

const ALLOWED_LIMITS = ["5", "10", "30", "50"];
const DEFAULT_LIMIT = "10";

const Search = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const limitParam = searchParams.get("limit") ?? DEFAULT_LIMIT;
  const initialLimit = ALLOWED_LIMITS.includes(limitParam) ? limitParam : DEFAULT_LIMIT;
  const initialExplicitCriteria = searchParams.get("mode") === "explicit"
    ? parseExplicitCriteria(searchParams.get("criteria")) : null;
  const [searchMode, setSearchMode] = React.useState<"natural" | "advanced">(
    initialExplicitCriteria ? "advanced" : "natural",
  );
  const [submittedQuery, setSubmittedQuery] = React.useState(initialQuery);
  const [pageOffset, setPageOffset] = React.useState(0);
  const [draftCriteria, setDraftCriteria] = React.useState<SearchInterpretation | null>(initialExplicitCriteria);
  const [advancedCriteria, setAdvancedCriteria] = React.useState<SearchInterpretation>(
    initialExplicitCriteria ?? emptySearchCriteria(),
  );
  const {
    handleSearch, handleExplicitSearch, sendFeedback, clearSearch,
    results, searchResponse, originSearchId, feedbackMessage, isLoading, message, isError,
  } = useSearch();

  React.useEffect(() => {
    if (searchMode === "natural" && searchResponse?.interpretation) {
      setDraftCriteria(searchResponse.interpretation);
    }
  }, [searchResponse, searchMode]);

  const formik = useFormik({
    initialValues: { search: initialQuery, searchLimit: initialLimit },
    onSubmit: async data => {
      const query = data.search.trim();
      setPageOffset(0);
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
    setPageOffset(0);
    setDraftCriteria(null);
    setAdvancedCriteria(emptySearchCriteria());
    setSearchParams({});
  };

  const applyCorrection = async () => {
    if (!draftCriteria) return;
    setPageOffset(0);
    setSubmittedQuery(draftCriteria.query ?? "");
    const searched = await handleExplicitSearch(draftCriteria, formik.values.searchLimit);
    if (searched) {
      setSearchParams(explicitSearchParams(draftCriteria, formik.values.searchLimit));
      if (originSearchId != null) await sendFeedback("partially_correct", draftCriteria);
    }
  };

  const switchToAdvanced = () => {
    setSearchMode("advanced");
    setAdvancedCriteria(current => current.query
      ? current : { ...current, query: formik.values.search.trim() || null });
  };

  const submitAdvanced = async () => {
    setPageOffset(0);
    setSubmittedQuery(advancedCriteria.query ?? "");
    const searched = await handleExplicitSearch(advancedCriteria, formik.values.searchLimit);
    if (searched) setSearchParams(explicitSearchParams(advancedCriteria, formik.values.searchLimit));
  };

  const changePage = async (nextOffset: number) => {
    const offset = Math.max(0, nextOffset);
    const searched = searchMode === "advanced"
      ? await handleExplicitSearch(advancedCriteria, formik.values.searchLimit, offset)
      : draftCriteria
        ? await handleExplicitSearch(draftCriteria, formik.values.searchLimit, offset)
        : await handleSearch(submittedQuery, formik.values.searchLimit, offset);
    if (searched !== false) setPageOffset(offset);
  };

  return (
    <div>
      <h2 style={{ marginBottom: 4 }}>Wyszukiwanie</h2>
      <div role="tablist" aria-label="Tryb wyszukiwania" style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <button type="button" role="tab" aria-selected={searchMode === "natural"} className="button"
          style={{ opacity: searchMode === "natural" ? 1 : .55 }}
          onClick={() => setSearchMode("natural")}>Proste (z Bielikiem)</button>
        <button type="button" role="tab" aria-selected={searchMode === "advanced"} className="button"
          style={{ opacity: searchMode === "advanced" ? 1 : .55 }}
          onClick={switchToAdvanced}>Zaawansowane (bez Bielika)</button>
      </div>

      {searchMode === "natural" ? (
        <form onSubmit={formik.handleSubmit}>
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
        </form>
      ) : (
        <div>
          <p style={{ marginTop: 0, color: "#64748b", fontSize: ".88rem" }}>
            Ustaw filtry bezpośrednio — to wyszukiwanie nigdy nie wywołuje Bielika.
          </p>
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 4 }}>
            <Select disabled={isLoading} value={formik.values.searchLimit} label="Liczba wyników"
              onChange={formik.handleChange} id="searchLimitAdvanced" name="searchLimit" type="text">
              {ALLOWED_LIMITS.map(limit => <option key={limit} value={limit}>{limit}</option>)}
            </Select>
            <button type="button" className="button" style={{ marginTop: 11 }} onClick={handleClean}>Wyczyść</button>
          </div>
          <SearchCriteriaEditor criteria={advancedCriteria} disabled={isLoading}
            onChange={setAdvancedCriteria} onApply={() => { void submitAdvanced(); }}
            title="Kryteria wyszukiwania" applyLabel="Szukaj" />
        </div>
      )}

      {isLoading && <div className="loader" />}
      {isError && <p className="errorText">{message}</p>}
      {searchMode === "natural" && searchResponse && !isLoading && (
        <SearchInterpretationPanel interpretation={searchResponse.interpretation}
          fallbackUsed={searchResponse.fallback_used} />
      )}
      {searchMode === "natural" && draftCriteria && !isLoading && (
        <SearchCriteriaEditor criteria={draftCriteria} disabled={isLoading}
          onChange={setDraftCriteria} onApply={() => { void applyCorrection(); }} />
      )}
      {searchMode === "natural" && originSearchId != null && !isLoading && (
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
      {results && !isLoading && (pageOffset > 0 || searchResponse?.pagination?.has_more) && (
        <nav aria-label="Stronicowanie wyników"
          style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 30 }}>
          <button type="button" className="button" disabled={pageOffset === 0}
            onClick={() => { void changePage(pageOffset - Number(formik.values.searchLimit)); }}>
            Poprzednia
          </button>
          <span style={{ color: "#475569", fontSize: ".88rem" }}>
            Strona {Math.floor(pageOffset / Number(formik.values.searchLimit)) + 1}
          </span>
          <button type="button" className="button" disabled={!searchResponse?.pagination?.has_more}
            onClick={() => { void changePage(pageOffset + Number(formik.values.searchLimit)); }}>
            Następna
          </button>
        </nav>
      )}
    </div>
  );
};

export default Search;
