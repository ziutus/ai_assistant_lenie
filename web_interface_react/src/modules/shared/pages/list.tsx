import React from "react";
import { useList } from "../hooks/useList";
import { useDocumentStates } from "../hooks/useDocumentStates";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { useManageLLM } from "../hooks/useManageLLM";
import { useFormik } from 'formik';
import { buildObsidianNoteUrl } from "../utils/obsidian";

const List = () => {
    const { isLoading, isError, data, message, handleGetList, dataAllLength } = useList();
    const { states: fetchedStates, types: fetchedTypes } = useDocumentStates();

  const formik: any = useFormik({
    initialValues: {
      id: "",
      search: ""
    },
    onSubmit: () => {},
  });

  const { selectedDocumentType, setSelectedDocumentType, selectedDocumentState, setSelectedDocumentState } = React.useContext(AuthorizationContext);
  const { searchInDocument, setSearchInDocument} = React.useContext(AuthorizationContext);
  const { searchType, setSearchType} = React.useContext(AuthorizationContext);
  const [obsidianFilter, setObsidianFilter] = React.useState<"none" | "missing" | "has">("none");

  const obsidianFilterParams = (filter: "none" | "missing" | "has") => ({
    onlyMissing: filter === "missing",
    onlyHas: filter === "has",
  });

  const { handleDeleteDocument } = useManageLLM({ formik, selectedDocumentType, selectedDocumentState });

  const handleTypeChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
          setSelectedDocumentType(event.target.value);
          handleGetList(event.target.value, selectedDocumentState, searchInDocument, obsidianFilterParams(obsidianFilter));
  };

  const handleDocumentStateChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
          setSelectedDocumentState(event.target.value);
          handleGetList(selectedDocumentType, event.target.value, searchInDocument, obsidianFilterParams(obsidianFilter));
  };

  const handleObsidianFilterChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
          const filter = event.target.value as "none" | "missing" | "has";
          setObsidianFilter(filter);
          handleGetList(selectedDocumentType, selectedDocumentState, searchInDocument, obsidianFilterParams(filter));
  };

  const handleDocumentDeleteOnThisPage = async (document_id: string | number) => {
    console.log("handleDocumentDeleteOnThisPage, page id: " + document_id);
    await handleDeleteDocument(String(document_id));
    handleGetList(selectedDocumentType, selectedDocumentState);
  };

  return (
    <div>
      <h2 style={{ marginBottom: "20px" }}>
        Lista Zapisanych Stron i linków {!!data && `(${data?.length} z ${dataAllLength})`}
      </h2>

      <select value={selectedDocumentType} onChange={handleTypeChange}>
        <option value="ALL">ALL</option>
        {fetchedTypes.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>

      <select value={selectedDocumentState} onChange={handleDocumentStateChange}>
        <option value="ALL">ALL</option>
        {fetchedStates.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <input
        type="text"
        id="search"
        name="search"
        size={40}
        value={searchInDocument}
        onChange={(event: React.ChangeEvent<HTMLInputElement>) => setSearchInDocument(event.target.value)}
        disabled={isLoading}
      />


        <input
          type="radio"
          id="strict"
          name="search_type"
          value="strict"
          checked={searchType === 'strict'}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) => setSearchType(event.target.value)}
          disabled={isLoading}
        />
        <label htmlFor="strict">Strict</label>

        <input
          type="radio"
          id="similar"
          name="search_type"
          value="similar"
          checked={searchType === 'similar'}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) => setSearchType(event.target.value)}
          disabled={isLoading}
        />
        <label htmlFor="similar">Similar</label>
      <button
        disabled={isLoading}
        className={"button"}
        type={"button"}
        onClick={() => handleGetList(selectedDocumentType, selectedDocumentState, searchInDocument, obsidianFilterParams(obsidianFilter))}
      >
        Search
      </button>
      <br />
      <label htmlFor="obsidian_filter"> 📝 Notatki Obsidian: </label>
      <select id="obsidian_filter" value={obsidianFilter} onChange={handleObsidianFilterChange} disabled={isLoading}>
        <option value="none">wszystkie</option>
        <option value="missing">tylko z brakującymi</option>
        <option value="has">tylko z notatką</option>
      </select>
      <div>
        <p className={"errorText"}>{message}</p>
      </div>

      {isLoading && (
        <div style={{ marginBottom: "10px" }} className={"loader"}></div>
      )}
      <ul>
        {data &&
          data.map((item: any) => (
            <li
              key={item.id}
              className={"flexBox"}
              style={{
                marginBottom: "7px",
                paddingBottom: "7px",
                borderBottom: "1px solid rgb(179, 179, 179)",
              }}
            >
              {item.id}&nbsp;&nbsp;|&nbsp;&nbsp;
              {item.title} &nbsp;
              {item.author && (
                <span style={{ color: "#6c757d", fontStyle: "italic" }}>({item.author}) </span>
              )}
              <a
                href={item.url}
                style={{ color: "rgba(0,122,255)" }}
                target="_blank"
                rel="noopener noreferrer"
              >
                {(item.title && item.title.length > 10) ? item.url.substring(0, 50) + '...' : item.url}
              </a>
              <span> {item.document_state}
                {item.document_state_error !== 'NONE' && ` | ${item.document_state_error}`}
              </span>
              {!!item.obsidian_note_paths?.length && (
                <span style={{ margin: "0 0 0 10px", color: "#15803d" }}>
                  📝{" "}
                  {item.obsidian_note_paths.map((notePath: string, i: number) => (
                    <React.Fragment key={notePath}>
                      {i > 0 && ", "}
                      <a href={buildObsidianNoteUrl(notePath)} title={`Otwórz w Obsidianie: ${notePath}`}>
                        {notePath.split("/").pop()?.replace(/\.md$/i, "")}
                      </a>
                    </React.Fragment>
                  ))}
                </span>
              )}
              {!!item.chunks_with_obsidian_notes && (
                <span
                  style={{ margin: "0 0 0 10px", color: "#15803d" }}
                  title="Chunki TEMAT z notatką Obsidian"
                >
                  📝 {item.chunks_with_obsidian_notes} gotowe
                </span>
              )}
              {!!item.chunks_missing_obsidian_notes && (
                <span
                  style={{ margin: "0 0 0 10px", color: "#7c3aed" }}
                  title="Chunki TEMAT bez notatki Obsidian"
                >
                  📝 {item.chunks_missing_obsidian_notes} do zrobienia
                </span>
              )}
              <span style={{ margin: "0 0 0 auto", fontWeight: "500" }}>
                {item.document_type}
              </span>
              <NavLink
                className={"button"}
                style={{ margin: "0 0 0 10px" }}
                onClick={() => {
                }}
                to={`/${item.document_type}/${item.id}`}
              >
                Edit
              </NavLink>
              {["youtube", "movie", "webpage", "text"].includes(item.document_type) && (
                <NavLink
                  className={"button"}
                  style={{ margin: "0 0 0 6px" }}
                  to={`/read/${item.id}`}
                >
                  Czytaj
                </NavLink>
              )}
              {["youtube", "movie", "webpage", "text"].includes(item.document_type) && (
                <NavLink
                  className={"button"}
                  style={{ margin: "0 0 0 6px" }}
                  to={`/chunks/${item.id}`}
                  state={{ docType: item.document_type }}
                >
                  Chunki
                </NavLink>
              )}
              <button
                className={"button"}
                style={{ margin: "0 0 0 10px" }}
                onClick={() => handleDocumentDeleteOnThisPage(item.id)}
              >
                Delete
              </button>
            </li>
          ))}
      </ul>
    </div>
  );
};

export default List;
