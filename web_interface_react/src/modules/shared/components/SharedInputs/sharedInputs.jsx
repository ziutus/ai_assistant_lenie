import React from "react";
import Input from "../Input/input";
import Select from "../Select/select";
import { NavLink } from "react-router-dom";

const SharedInputs = ({
  formik,
  isLoading,
  handleGetLinkByID,
  handleGetEntryToReview,
  handleGetPageByUrl,
}) => {
  return (
    <>
      <Input
        disabled={isLoading}
        value={formik.values.author}
        label={"Author"}
        onChange={formik.handleChange}
        id={"author"}
        name={"author"}
        type={"text"}
      />
      <div className="flexBox">
        <div className="flex-grow">
          <Input
            disabled={isLoading}
            value={formik.values.id}
            label={"Document ID"}
            onChange={formik.handleChange}
            id={"id"}
            name={"id"}
            type={"text"}
          />
        </div>
        <button
          disabled={isLoading}
          className={"button"}
          style={{ marginTop: "13px", marginLeft: "10px" }}
          onClick={() => handleGetLinkByID(formik.values.id)}
        >
          read
        </button>
        {formik.values.previous_id && formik.values.previous_type && (
          <NavLink
            to={`/${formik.values.previous_type}/${formik.values.previous_id}`}
            disabled={isLoading}
            className={"button"}
            style={{ marginTop: "13px", marginLeft: "10px" }}
          >
            ({formik.values.previous_id}) previous
          </NavLink>
        )}
        {formik.values.next_id && formik.values.next_type && (
          <NavLink
            to={`/${formik.values.next_type}/${formik.values.next_id}`}
            disabled={isLoading}
            className={"button"}
            style={{ marginTop: "13px", marginLeft: "10px" }}
          >
            ({formik.values.next_id}) next
          </NavLink>
        )}
        <button
          disabled={isLoading}
          className={"button"}
          style={{ marginTop: "13px", marginLeft: "10px" }}
          onClick={() => formik.resetForm()}
        >
          clean
        </button>
        <button
          disabled={isLoading}
          className={"button"}
          style={{ marginTop: "13px", marginLeft: "10px" }}
          onClick={() => handleGetEntryToReview(formik.values)}
        >
          Next To review
        </button>
      </div>
      <Input
        disabled={isLoading}
        value={formik.values.source}
        label={"Source"}
        onChange={formik.handleChange}
        id={"source"}
        name={"source"}
        type={"text"}
      />
      <Input
        disabled={isLoading}
        value={formik.values.language}
        label={"Language"}
        onChange={formik.handleChange}
        id={"language"}
        name={"language"}
        type={"text"}
      />
      {formik.values.document_state_error && (
        <div>
          <p style={{ marginBottom: "10px", fontSize: "15px" }}>
            Document state error: {formik.values.document_state_error}
          </p>
        </div>
      )}
      <Select
        disabled={isLoading}
        value={formik.values.document_state}
        label={"Document state"}
        onChange={formik.handleChange}
        id={"document_state"}
        name={"document_state"}
        type={"text"}
      >
        <option value="NONE">DEFAULT NONE state</option>
        <option value="ERROR_DOWNLOAD">ERROR_DOWNLOAD</option>
        <option value="URL_ADDED">URL_ADDED</option>
        <option value="NEED_TRANSCRIPTION">NEED_TRANSCRIPTION</option>
        <option value="TRANSCRIPTION_DONE">TRANSCRIPTION_DONE</option>
        <option value="TRANSCRIPTION_IN_PROGRESS">
          TRANSCRIPTION_IN_PROGRESS
        </option>
        <option value="NEED_MANUAL_REVIEW">NEED_MANUAL_REVIEW</option>
        <option value="READY_FOR_TRANSLATION">READY_FOR_TRANSLATION</option>
        <option value="READY_FOR_EMBEDDING">READY_FOR_EMBEDDING</option>
        <option value="EMBEDDING_EXIST">EMBEDDING_EXIST</option>
      </Select>

      <div className="flexBox">
        <div className="flex-grow">
          <Input
            disabled={isLoading}
            value={formik.values.url}
            label={"Link"}
            onChange={formik.handleChange}
            id={"url"}
            name={"url"}
            type={"text"}
          />
        </div>
        <a
          className={
            isLoading || formik.values.url === "" ? "button disabled" : "button"
          }
          style={{ marginTop: "13px", marginLeft: "10px" }}
          href={formik.values.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open
        </a>
        <button
          disabled={isLoading || formik.values.url === ""}
          style={{ marginTop: "13px", marginLeft: "10px" }}
          className={"button"}
          onClick={() => handleGetPageByUrl(formik.values.url)}
        >
          read
        </button>
      </div>

      <Input
        disabled={isLoading}
        value={formik.values.title}
        label={"Title"}
        onChange={formik.handleChange}
        id={"title"}
        name={"title"}
        type={"text"}
      />
      <Input
        disabled={isLoading}
        value={formik.values.summary}
        label={"Summary"}
        onChange={formik.handleChange}
        id={"summary"}
        name={"summary"}
        type={"text"}
      />
      <Input
        disabled={isLoading}
        value={formik.values.language}
        label={"Language"}
        onChange={formik.handleChange}
        id={"language"}
        name={"language"}
        type={"text"}
      />
      <Input
        disabled={isLoading}
        value={formik.values.tags}
        label={"Tags"}
        onChange={formik.handleChange}
        id={"tags"}
        name={"tags"}
        type={"text"}
      />
    </>
  );
};

export default SharedInputs;
