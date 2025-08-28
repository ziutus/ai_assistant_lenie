import React from "react";
import ListItemSearchSimilar from "../../../utils";
import { useFormik } from "formik";
import Input from "../components/Input/input";
import { useSearch } from "../hooks/useSearch";
import Select from "../components/Select/select";

const Search = () => {
  const { handleSearchSimilar, results, setResults, isLoading, message, setMessage, isError } =
      useSearch({
        callback: () => formik.resetForm(),
      });

  const handleClean = () => {
    formik.resetForm();
    setResults([]);
    setMessage("");
  };

  const formik = useFormik({
    initialValues: {
      search: "",      // Pole 'search'
      searchLimit: "", // Dodane pole 'searchLimit'
      translate: false
    },
    onSubmit: async (data) => {
      await handleSearchSimilar(data.search, data.searchLimit, data.translate);
    },
  });

  return (
      <form onSubmit={formik.handleSubmit}>
        <h2 style={{ marginBottom: "10px" }}>Search Similar</h2>
        <div style={{display: "flex", alignItems: "center"}}>
          <div style={{minWidth: "400px", marginRight: "20px"}}>
            <Input
                required
                disabled={isLoading}
                value={formik.values.search}
                label={"Search"}
                onChange={formik.handleChange}
                id={"search"}
                name={"search"}
                type={"text"}
            />
          </div>

          <Select
              disabled={isLoading}
              value={formik.values.searchLimit} // Zaktualizowane pole wartości z Formika
              label={"search Limit"}
              onChange={formik.handleChange} // Dodana obsługa zmiany wartości z Formika
              id={"searchLimit"}
              name={"searchLimit"}
              type={"text"}
          >
            <option value="5">5</option>
            <option value="10">10</option>
            <option value="30">30</option>
            <option value="50">50</option>
          </Select>

          <div style={{marginLeft: '20px'}}>
            <label htmlFor="translate" style={{marginRight: '10px'}}>Translate</label>
            <input
                type="checkbox"
                id="translate"
                name="translate"
                checked={formik.values.translate}
                onChange={formik.handleChange}
                disabled={isLoading}
            />
          </div>

          <button
              type={"submit"}
              style={{marginTop: "11px"}}
              className={"button"}
              disabled={isLoading}
          >
            Search
          </button>

          <button
              className={"button"}
              style={{marginTop: "11px", marginLeft: "10px"}}
              onClick={() => handleClean()}
          >
            Clean
          </button>
        </div>

        {isLoading && <div className={"loader"}></div>}
        {isError && <p className={"errorText"}>{message}</p>}

        <ul>
          {results?.map((item) => (
              <ListItemSearchSimilar key={item.id} item={item}/>
          ))}
        </ul>
      </form>
  );
};

export default Search;
