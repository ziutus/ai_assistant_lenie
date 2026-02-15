import React, { useState } from "react";
import { useList } from "../hooks/useList";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { useManageLLM } from "../hooks/useManageLLM";
import { useFormik } from 'formik';
import Input from '../components/Input/input';

const List = () => {
    const { isLoading, isError, data, message, handleGetList, dataAllLength } = useList();

  const formik = useFormik({
    initialValues: {
      id: "",
      search: ""
    },
    onSubmit: () => {},
  });

  const { selectedDocumentType, setSelectedDocumentType, selectedDocumentState, setSelectedDocumentState} = React.useContext(AuthorizationContext);
  const { searchInDocument, setSearchInDocument} = React.useContext(AuthorizationContext);
  const { searchType, setSearchType} = React.useContext(AuthorizationContext);

  const { handleDeleteDocument } = useManageLLM({ formik, selectedDocumentType, selectedDocumentState });

  const handleTypeChange = (event) => {
          setSelectedDocumentType(event.target.value);
          handleGetList(event.target.value, selectedDocumentState,searchInDocument); // Pass both type and documentState
  };

  const handleDocumentStateChange = (event) => {
          setSelectedDocumentState(event.target.value);
          handleGetList(selectedDocumentType, event.target.value,searchInDocument); // Pass both type and documentState
  };

  const handleDocumentDeleteOnThisPage = async (document_id) => {
    console.log("handleDocumentDeleteOnThisPage, page id: " + document_id);
    await handleDeleteDocument(document_id);
    handleGetList(selectedDocumentType, selectedDocumentState);
  };

  return (
    <div>
      <h2 style={{ marginBottom: "20px" }}>
        Lista Zapisanych Stron i linków {!!data && `(${data?.length} z ${dataAllLength})`}
      </h2>

      <select value={selectedDocumentType} onChange={handleTypeChange}>
        <option value="ALL">ALL</option>
        <option value="webpage">webpage</option>
        <option value="link">link</option>
        <option value="youtube">youtube</option>
        <option value="movie">movie</option>
      </select>

      <select value={selectedDocumentState} onChange={handleDocumentStateChange}>
        <option value="ALL">ALL</option>
        <option value="URL_ADDED">URL_ADDED</option>
        <option value="NEED_MANUAL_REVIEW">NEED_MANUAL_REVIEW</option>
        <option value="EMBEDDING_EXIST">EMBEDDING_EXIST</option>
        <option value="READY_FOR_TRANSLATION">READY_FOR_TRANSLATION</option>
        <option value="ERROR">ERROR</option>
      </select>
      <input
        type="text"
        id="search"
        name="search"
        size={40}
        value={searchInDocument}
        onChange={(event) => setSearchInDocument(event.target.value)}
        disabled={isLoading}
      />


        <input
          type="radio"
          id="strict"
          name="search_type"
          value="strict"
          checked={searchType === 'strict'}
          onChange={(event) => setSearchType(event.target.value)}
          disabled={isLoading}
        />
        <label htmlFor="strict">Strict</label>

        <input
          type="radio"
          id="similar"
          name="search_type"
          value="similar"
          checked={searchType === 'similar'}
          onChange={(event) => setSearchType(event.target.value)}
          disabled={isLoading}
        />
        <label htmlFor="similar">Similar</label>
      <button
        disabled={isLoading}
        className={"button"}
        type={"button"}
        onClick={() => handleGetList(selectedDocumentType, selectedDocumentState, searchInDocument)}
      >
        Search
      </button>
      <div>
        <p className={"errorText"}>{message}</p>
      </div>

      {isLoading && (
        <div style={{ marginBottom: "10px" }} className={"loader"}></div>
      )}
      <ul>
        {data &&
          data.map((item) => (
            <li
              key={item.id}
              className={"flexBox"}
              style={{
                marginBottom: "7px",
                paddingBottom: "7px",
                borderBottom: "1px solid rgb(179, 179, 179)",
                "&:hover": {
                  borderColor: "red",
                },
              }}
            >
              {item.id}&nbsp;&nbsp;|&nbsp;&nbsp;
              {item.title} &nbsp;
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
              <button
                className={"button"}
                style={{ margin: "0 0 0 10px" }}
                // onClick={() => handleDeleteDocument(item.id)}
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
