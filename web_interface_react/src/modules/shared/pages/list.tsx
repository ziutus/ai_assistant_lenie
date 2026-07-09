import React from "react";
import { useList } from "../hooks/useList";
import { useDocumentStates } from "../hooks/useDocumentStates";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { useManageLLM } from "../hooks/useManageLLM";
import { useFormik } from 'formik';
import { buildObsidianNoteUrl } from "../utils/obsidian";

// States where a document has no usable text yet — showing "Czytaj"/"Chunki" there
// would just open an empty page. Mirrors the backend's YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES
// (minus TEMPORARY_ERROR's overlap) plus TRANSCRIPTION_IN_PROGRESS.
const NO_TEXT_STATES = ["URL_ADDED", "NEED_TRANSCRIPTION", "TRANSCRIPTION_IN_PROGRESS", "TEMPORARY_ERROR"];

// Mirrors backend's _YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES — retry is only safe
// before a transcript has ever been captured, so it can't clobber reviewed text.
const YOUTUBE_CAPTIONS_RETRY_STATES = ["TEMPORARY_ERROR", "URL_ADDED", "NEED_TRANSCRIPTION"];

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
  const [expandedObsidian, setExpandedObsidian] = React.useState<Set<number>>(new Set());

  const toggleObsidianExpanded = (id: number) => {
    setExpandedObsidian(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const obsidianFilterParams = (filter: "none" | "missing" | "has") => ({
    onlyMissing: filter === "missing",
    onlyHas: filter === "has",
  });

  const { handleDeleteDocument, handleYoutubeRetryCaptions, message: manageMessage, isLoading: isRetrying } = useManageLLM({ formik, selectedDocumentType, selectedDocumentState });

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

  const handleRetryCaptionsOnThisPage = async (document_id: string | number) => {
    await handleYoutubeRetryCaptions(document_id);
    handleGetList(selectedDocumentType, selectedDocumentState, searchInDocument, obsidianFilterParams(obsidianFilter));
  };

  // Single compact indicator for the row — details (links, counts) live in an
  // expandable panel instead of cluttering the main line with several badges.
  const obsidianSummary = (item: any) => {
    const hasDocNotes = !!item.obsidian_note_paths?.length;
    const hasChunkNotes = !!item.chunks_with_obsidian_notes;
    const hasTodo = !!item.chunks_missing_obsidian_notes;
    if (!hasDocNotes && !hasChunkNotes && !hasTodo) return null;

    let label: string;
    let color: string;
    if (hasTodo && !hasDocNotes && !hasChunkNotes) {
      label = `📝 ${item.chunks_missing_obsidian_notes} do zrobienia`;
      color = "#7c3aed";
    } else if (hasTodo) {
      label = "📝 częściowo opracowane";
      color = "#b45309";
    } else {
      label = "📝 notatka";
      color = "#15803d";
    }
    return { label, color };
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
        {manageMessage && <p className={"errorText"}>{manageMessage}</p>}
      </div>

      {isLoading && (
        <div style={{ marginBottom: "10px" }} className={"loader"}></div>
      )}
      <ul>
        {data &&
          data.map((item: any) => {
            const obsidian = obsidianSummary(item);
            const isExpanded = expandedObsidian.has(item.id);
            return (
            <li
              key={item.id}
              style={{
                marginBottom: "7px",
                paddingBottom: "7px",
                borderBottom: "1px solid rgb(179, 179, 179)",
              }}
            >
            <div className={"flexBox"}>
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
              {obsidian && (
                <span
                  onClick={() => toggleObsidianExpanded(item.id)}
                  style={{ margin: "0 0 0 10px", color: obsidian.color, cursor: "pointer", fontWeight: 500 }}
                  title="Kliknij, aby zobaczyć szczegóły notatek Obsidian"
                >
                  {obsidian.label} {isExpanded ? "▾" : "▸"}
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
              {["youtube", "movie", "webpage", "text"].includes(item.document_type) && !NO_TEXT_STATES.includes(item.document_state) && (
                <NavLink
                  className={"button"}
                  style={{ margin: "0 0 0 6px" }}
                  to={`/read/${item.id}`}
                >
                  Czytaj
                </NavLink>
              )}
              {["youtube", "movie", "webpage", "text"].includes(item.document_type) && !NO_TEXT_STATES.includes(item.document_state) && (
                <NavLink
                  className={"button"}
                  style={{ margin: "0 0 0 6px" }}
                  to={`/chunks/${item.id}`}
                  state={{ docType: item.document_type }}
                >
                  Chunki
                </NavLink>
              )}
              {item.document_type === "youtube" && YOUTUBE_CAPTIONS_RETRY_STATES.includes(item.document_state) && (
                <button
                  className={"button"}
                  style={{ margin: "0 0 0 6px" }}
                  disabled={isRetrying}
                  onClick={() => handleRetryCaptionsOnThisPage(item.id)}
                >
                  Pobierz napisy ponownie
                </button>
              )}
              <button
                className={"button"}
                style={{ margin: "0 0 0 10px" }}
                onClick={() => handleDocumentDeleteOnThisPage(item.id)}
              >
                Delete
              </button>
            </div>
            {isExpanded && obsidian && (
              <div style={{ marginTop: 6, paddingLeft: 20, fontSize: "0.85em", color: "#475569" }}>
                {!!item.obsidian_note_paths?.length && (
                  <div>
                    Notatka dokumentu:{" "}
                    {item.obsidian_note_paths.map((notePath: string, i: number) => (
                      <React.Fragment key={notePath}>
                        {i > 0 && ", "}
                        <a href={buildObsidianNoteUrl(notePath)} title={`Otwórz w Obsidianie: ${notePath}`}>
                          {notePath.split("/").pop()?.replace(/\.md$/i, "")}
                        </a>
                      </React.Fragment>
                    ))}
                  </div>
                )}
                {(!!item.chunks_with_obsidian_notes || !!item.chunks_missing_obsidian_notes) && (
                  <div>
                    Chunki: {item.chunks_with_obsidian_notes || 0} gotowych, {item.chunks_missing_obsidian_notes || 0} do zrobienia —{" "}
                    <NavLink to={`/chunks/${item.id}`} state={{ docType: item.document_type }}>
                      przejdź do przeglądu chunków
                    </NavLink>
                  </div>
                )}
              </div>
            )}
            </li>
            );
          })}
      </ul>
    </div>
  );
};

export default List;
