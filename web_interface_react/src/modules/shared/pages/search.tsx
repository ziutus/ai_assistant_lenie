import React from "react";
import ListItemSearchSimilar from "../../../utils";
import { useFormik } from "formik";
import Input from "../components/Input/input";
import { useSearch } from "../hooks/useSearch";
import Select from "../components/Select/select";
import { useSearchParams } from "react-router-dom";

const ALLOWED_LIMITS = ["5", "10", "30", "50"];
const DEFAULT_LIMIT = "10";

const copyToClipboard = (text: string): boolean => {
  if (navigator.clipboard && window.isSecureContext) {
    void navigator.clipboard.writeText(text);
    return true;
  }
  // Fallback dla http:// (brak secure context, np. NAS po IP)
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(textarea);
  return ok;
};

const Search = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const limitParam = searchParams.get("limit") ?? DEFAULT_LIMIT;
  const initialLimit = ALLOWED_LIMITS.includes(limitParam) ? limitParam : DEFAULT_LIMIT;
  const initialTranslate = searchParams.get("translate") === "true";
  const [submittedQuery, setSubmittedQuery] = React.useState(initialQuery);
  const [copied, setCopied] = React.useState(false);
  const { handleSearchSimilar, results, setResults, isLoading, message, setMessage, isError } =
      useSearch({
        callback: () => formik.resetForm(),
      });

  const handleClean = () => {
    formik.resetForm({ values: { search: "", searchLimit: DEFAULT_LIMIT, translate: false } });
    setResults([]);
    setMessage("");
    setSubmittedQuery("");
    setSearchParams({});
  };

  const handleCopyLink = () => {
    if (copyToClipboard(window.location.href)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const formik: any = useFormik({
    initialValues: {
      search: initialQuery,
      searchLimit: initialLimit,
      translate: initialTranslate
    },
    onSubmit: async (data) => {
      const query = data.search.trim();
      setSubmittedQuery(query);
      const params: Record<string, string> = { q: query };
      if (data.searchLimit !== DEFAULT_LIMIT) params.limit = data.searchLimit;
      if (data.translate) params.translate = "true";
      setSearchParams(params);
      await handleSearchSimilar(query, data.searchLimit, data.translate);
    },
  });

  const initialSearchDone = React.useRef(false);
  React.useEffect(() => {
    if (!initialSearchDone.current && initialQuery) {
      initialSearchDone.current = true;
      void handleSearchSimilar(initialQuery, initialLimit, initialTranslate);
    }
  }, [handleSearchSimilar, initialQuery, initialLimit, initialTranslate]);

  return (
      <form onSubmit={formik.handleSubmit}>
        <h2 style={{ marginBottom: "4px" }}>Wyszukiwanie</h2>
        <p style={{ marginTop: 0, color: "#64748b", fontSize: ".88rem" }}>Wyniki łączą dopasowanie tekstowe i semantyczne.</p>
        <div style={{display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12}}>
          <div style={{minWidth: "min(520px, 100%)", flex: "1 1 420px"}}>
            <Input
                required
                disabled={isLoading}
                value={formik.values.search}
                label={"Szukana fraza"}
                onChange={formik.handleChange}
                id={"search"}
                name={"search"}
                type={"text"}
            />
          </div>

          <Select
              disabled={isLoading}
              value={formik.values.searchLimit}
              label={"Liczba wyników"}
              onChange={formik.handleChange}
              id={"searchLimit"}
              name={"searchLimit"}
              type={"text"}
          >
            <option value="5">5</option>
            <option value="10">10</option>
            <option value="30">30</option>
            <option value="50">50</option>
          </Select>

          <button
              type={"submit"}
              style={{marginTop: "11px"}}
              className={"button"}
              disabled={isLoading}
          >
            Szukaj
          </button>

          <button
              type={"button"}
              className={"button"}
              style={{marginTop: "11px", marginLeft: "10px"}}
              onClick={() => handleClean()}
          >
            Wyczyść
          </button>

          {submittedQuery && (
            <button
                type={"button"}
                className={"button"}
                style={{marginTop: "11px", marginLeft: "10px"}}
                onClick={() => handleCopyLink()}
            >
              {copied ? "Skopiowano ✓" : "📋 Kopiuj link"}
            </button>
          )}
        </div>

        {isLoading && <div className={"loader"}></div>}
        {isError && <p className={"errorText"}>{message}</p>}

        {results && !isLoading && (
          <div style={{ margin: "18px 0 10px", color: "#64748b", fontSize: ".85rem" }}>
            Znaleziono: <strong style={{ color: "#334155" }}>{results.length}</strong>
          </div>
        )}
        <div style={{ display: "grid", gap: 12, maxWidth: 1050, paddingBottom: 30 }}>
          {results?.map((item: any) => (
              <ListItemSearchSimilar key={`${item.website_id}-${item.chunk_id ?? item.id ?? "text"}`} item={item} query={submittedQuery}/>
          ))}
        </div>
      </form>
  );
};

export default Search;
