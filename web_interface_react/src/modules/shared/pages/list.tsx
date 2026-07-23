import React from "react";
import { useList } from "../hooks/useList";
import { useDocumentStates } from "../hooks/useDocumentStates";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { useManageLLM } from "../hooks/useManageLLM";
import { useFormik } from 'formik';
import { buildObsidianNoteUrl } from "../utils/obsidian";
import { loadListFilters, saveListFilters } from "../services/storage";

// States where a document has no usable text yet — showing "Czytaj"/"Chunki" there
// would just open an empty page. Mirrors the backend's YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES
// (minus TEMPORARY_ERROR's overlap) plus TRANSCRIPTION_IN_PROGRESS.
const NO_TEXT_STATES = ["URL_ADDED", "NEED_TRANSCRIPTION", "TRANSCRIPTION_IN_PROGRESS", "TEMPORARY_ERROR"];

// Mirrors backend's _YOUTUBE_CAPTIONS_RETRY_ALLOWED_STATES — retry is only safe
// before a transcript has ever been captured, so it can't clobber reviewed text.
const YOUTUBE_CAPTIONS_RETRY_STATES = ["TEMPORARY_ERROR", "URL_ADDED", "NEED_TRANSCRIPTION"];

const List = () => {
    const [searchParams, setSearchParams] = useSearchParams();
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
  const initialObsidian = searchParams.get("obsidian");
  const [obsidianFilter, setObsidianFilter] = React.useState<"none" | "missing" | "has">(
    initialObsidian === "missing" || initialObsidian === "has"
      ? initialObsidian : loadListFilters().obsidianFilter,
  );
  const parsedPage = Number(searchParams.get("page") ?? "1");
  const parsedPageSize = Number(searchParams.get("page_size") ?? "100");
  const [page, setPage] = React.useState(Number.isInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1);
  const [pageSize, setPageSize] = React.useState(
    [25, 50, 100].includes(parsedPageSize) ? parsedPageSize : 100,
  );
  const [withoutEmbedding, setWithoutEmbedding] = React.useState(
    searchParams.get("without_embedding") === "1",
  );
  const [copyMessage, setCopyMessage] = React.useState("");
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

  const listUrlParams = (
    type: string, state: string, query: string, obsidian: "none" | "missing" | "has",
    nextPage: number, nextPageSize: number, nextWithoutEmbedding: boolean,
  ) => {
    const params: Record<string, string> = {};
    if (type !== "ALL") params.type = type;
    if (state !== "ALL") params.status = state;
    if (query.trim()) params.q = query.trim();
    if (obsidian !== "none") params.obsidian = obsidian;
    if (nextPage !== 1) params.page = String(nextPage);
    if (nextPageSize !== 100) params.page_size = String(nextPageSize);
    if (nextWithoutEmbedding) params.without_embedding = "1";
    return params;
  };

  const loadPage = async (
    nextPage: number, type = selectedDocumentType, state = selectedDocumentState,
    query = searchInDocument, obsidian = obsidianFilter, nextPageSize = pageSize,
    nextWithoutEmbedding = withoutEmbedding,
  ) => {
    setPage(nextPage);
    setPageSize(nextPageSize);
    setWithoutEmbedding(nextWithoutEmbedding);
    setSearchParams(listUrlParams(
      type, state, query, obsidian, nextPage, nextPageSize, nextWithoutEmbedding,
    ));
    await handleGetList(
      type, state, query, obsidianFilterParams(obsidian), nextPage, nextPageSize,
      nextWithoutEmbedding,
    );
  };

  const initialLoadDone = React.useRef(false);
  React.useEffect(() => {
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;
    const type = searchParams.get("type") ?? selectedDocumentType;
    const state = searchParams.get("status") ?? selectedDocumentState;
    const query = searchParams.get("q") ?? searchInDocument;
    setSelectedDocumentType(type);
    setSelectedDocumentState(state);
    setSearchInDocument(query);
    void loadPage(page, type, state, query, obsidianFilter, pageSize, withoutEmbedding);
    // URL parameters are intentionally read once; later changes go through loadPage().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { handleDeleteDocument, handleYoutubeRetryCaptions, message: manageMessage, isLoading: isRetrying } = useManageLLM({ formik, selectedDocumentType, selectedDocumentState });

  const handleTypeChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
          setSelectedDocumentType(event.target.value);
          void loadPage(1, event.target.value);
  };

  const handleDocumentStateChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
          setSelectedDocumentState(event.target.value);
          void loadPage(1, selectedDocumentType, event.target.value);
  };

  const handleObsidianFilterChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
          const filter = event.target.value as "none" | "missing" | "has";
          setObsidianFilter(filter);
          saveListFilters({ obsidianFilter: filter });
          void loadPage(1, selectedDocumentType, selectedDocumentState, searchInDocument, filter);
  };

  const handleDocumentDeleteOnThisPage = async (document_id: string | number) => {
    console.log("handleDocumentDeleteOnThisPage, page id: " + document_id);
    await handleDeleteDocument(String(document_id));
    void loadPage(page);
  };

  const handleRetryCaptionsOnThisPage = async (document_id: string | number) => {
    await handleYoutubeRetryCaptions(document_id);
    void loadPage(page);
  };

  const copyListLink = async () => {
    const url = window.location.href;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        const input = document.createElement("textarea");
        input.value = url;
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        document.execCommand("copy");
        document.body.removeChild(input);
      }
      setCopyMessage("Link skopiowany");
    } catch {
      setCopyMessage("Nie udało się skopiować linku");
    }
  };

  const totalPages = Math.max(1, Math.ceil(dataAllLength / pageSize));
  const visiblePages = Array.from({ length: totalPages }, (_, index) => index + 1)
    .filter(number => number === 1 || number === totalPages || Math.abs(number - page) <= 2);

  const pagination = (position: "top" | "bottom") => data && totalPages > 1 ? (
    <nav aria-label={`Stronicowanie listy (${position === "top" ? "góra" : "dół"})`}
      style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6,
        padding: position === "top" ? "14px 0 8px" : "8px 0 30px" }}>
      <button type="button" className="button" disabled={isLoading || page <= 1}
        onClick={() => { void loadPage(page - 1); }}>Poprzednia</button>
      {visiblePages.map((number, index) => {
        const previous = visiblePages[index - 1];
        return (
          <React.Fragment key={number}>
            {previous && number - previous > 1 && <span>…</span>}
            <button type="button" className="button" disabled={isLoading || number === page}
              aria-current={number === page ? "page" : undefined}
              onClick={() => { void loadPage(number); }}
              style={{ minWidth: 36, opacity: number === page ? .6 : 1 }}>
              {number}
            </button>
          </React.Fragment>
        );
      })}
      <button type="button" className="button" disabled={isLoading || page >= totalPages}
        onClick={() => { void loadPage(page + 1); }}>Następna</button>
    </nav>
  ) : null;

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
        onClick={() => { void loadPage(1); }}
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
      <label htmlFor="page_size" style={{ marginLeft: 12 }}> Wyników na stronę: </label>
      <select id="page_size" value={pageSize} disabled={isLoading}
        onChange={event => { void loadPage(1, selectedDocumentType, selectedDocumentState,
          searchInDocument, obsidianFilter, Number(event.target.value)); }}>
        {[25, 50, 100].map(size => <option key={size} value={size}>{size}</option>)}
      </select>
      <label style={{ marginLeft: 12 }}>
        <input type="checkbox" checked={withoutEmbedding} disabled={isLoading}
          onChange={event => { void loadPage(
            1, selectedDocumentType, selectedDocumentState, searchInDocument,
            obsidianFilter, pageSize, event.target.checked,
          ); }} />
        Without embedding
      </label>
      <button type="button" className="button" disabled={isLoading}
        style={{ marginLeft: 12 }} onClick={() => { void copyListLink(); }}>
        Kopiuj link
      </button>
      {copyMessage && <span role="status" style={{ marginLeft: 8, fontSize: ".85rem" }}>{copyMessage}</span>}
      {pagination("top")}
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
              {item.byline && (
                <span style={{ color: "#6c757d", fontStyle: "italic" }}>({item.byline}) </span>
              )}
              <a
                href={item.url}
                style={{ color: "rgba(0,122,255)" }}
                target="_blank"
                rel="noopener noreferrer"
              >
                {(item.title && item.title.length > 10) ? item.url.substring(0, 50) + '...' : item.url}
              </a>
              <span> {item.processing_status}
                {item.processing_error_code !== 'NONE' && ` | ${item.processing_error_code}`}
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
              {["youtube", "movie", "webpage", "text"].includes(item.document_type) && !NO_TEXT_STATES.includes(item.processing_status) && (
                <NavLink
                  className={"button"}
                  style={{ margin: "0 0 0 6px" }}
                  to={`/read/${item.id}`}
                >
                  Czytaj
                </NavLink>
              )}
              {["youtube", "movie", "webpage", "text"].includes(item.document_type) && !NO_TEXT_STATES.includes(item.processing_status) && (
                <NavLink
                  className={"button"}
                  style={{ margin: "0 0 0 6px" }}
                  to={`/chunks/${item.id}`}
                  state={{ docType: item.document_type }}
                >
                  Chunki
                </NavLink>
              )}
              {item.document_type === "youtube" && YOUTUBE_CAPTIONS_RETRY_STATES.includes(item.processing_status) && (
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
      {pagination("bottom")}
    </div>
  );
};

export default List;
