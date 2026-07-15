import React from "react";
import ListItemSearchSimilar from "../../../utils";
import { useFormik } from "formik";
import Input from "../components/Input/input";
import { useSearch } from "../hooks/useSearch";
import Select from "../components/Select/select";
import { useSearchParams } from "react-router-dom";

const Search = () => {
  const [searchParams] = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const [submittedQuery, setSubmittedQuery] = React.useState(initialQuery);
  const { handleSearchSimilar, results, setResults, isLoading, message, setMessage, isError } =
      useSearch({
        callback: () => formik.resetForm(),
      });

  const handleClean = () => {
    formik.resetForm();
    setResults([]);
    setMessage("");
    setSubmittedQuery("");
  };

  const formik: any = useFormik({
    initialValues: {
      search: initialQuery,
      searchLimit: "10",
      translate: false
    },
    onSubmit: async (data) => {
      setSubmittedQuery(data.search.trim());
      await handleSearchSimilar(data.search, data.searchLimit, data.translate);
    },
  });

  const initialSearchDone = React.useRef(false);
  React.useEffect(() => {
    if (!initialSearchDone.current && initialQuery) {
      initialSearchDone.current = true;
      void handleSearchSimilar(initialQuery, "10", false);
    }
  }, [handleSearchSimilar, initialQuery]);

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
              className={"button"}
              style={{marginTop: "11px", marginLeft: "10px"}}
              onClick={() => handleClean()}
          >
            Wyczyść
          </button>
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
