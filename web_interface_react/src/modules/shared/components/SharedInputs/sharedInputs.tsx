import React from "react";
import axios from "axios";
import Input from "../Input/input";
import Select from "../Select/select";
import TagsInput from "../TagsInput/tagsInput";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";

interface SharedInputsProps {
  formik: any;
  isLoading: boolean;
  handleGetLinkByID: (id: string) => void;
  handleGetEntryToReview: (values: any) => void;
  handleGetPageByUrl: (url: string) => void;
}

// Languages the user actually works with — anything else via "inny…"
const PREFERRED_LANGUAGES = ["pl", "en"];

const LanguageSelect = ({ formik, isLoading }: { formik: any; isLoading: boolean }) => {
  const value: string = formik.values.language ?? "";
  const [custom, setCustom] = React.useState(false);
  const knownValue = value === "" || PREFERRED_LANGUAGES.includes(value);
  return (
    <>
      <Select
        disabled={isLoading}
        value={custom ? "__other__" : value}
        label={"Language"}
        id={"language-select"}
        onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
          if (e.target.value === "__other__") {
            setCustom(true);
            return;
          }
          setCustom(false);
          formik.setFieldValue("language", e.target.value);
        }}
      >
        <option value="">—</option>
        {PREFERRED_LANGUAGES.map((lang) => (
          <option key={lang} value={lang}>{lang}</option>
        ))}
        {!knownValue && !custom && <option value={value}>{value}</option>}
        <option value="__other__">inny…</option>
      </Select>
      {custom && (
        <Input
          disabled={isLoading}
          value={value}
          label={"Language (kod, np. de)"}
          onChange={formik.handleChange}
          id={"language"}
          name={"language"}
          type={"text"}
        />
      )}
    </>
  );
};

// Active sources from GET /sources?active=1; the current value stays visible
// even when it is deactivated/legacy (extra option), and "inne…" allows a free
// value — the backend auto-creates unknown sources on save.
const SourceSelect = ({ formik, isLoading, sources }: { formik: any; isLoading: boolean; sources: string[] }) => {
  const value: string = formik.values.source ?? "";
  const [custom, setCustom] = React.useState(false);
  const knownValue = value === "" || sources.includes(value);
  return (
    <>
      <Select
        disabled={isLoading}
        value={custom ? "__other__" : value}
        label={"Source"}
        id={"source-select"}
        onChange={(e: React.ChangeEvent<HTMLSelectElement>) => {
          if (e.target.value === "__other__") {
            setCustom(true);
            return;
          }
          setCustom(false);
          formik.setFieldValue("source", e.target.value);
        }}
      >
        <option value="">—</option>
        {sources.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
        {!knownValue && !custom && <option value={value}>{value}</option>}
        <option value="__other__">inne…</option>
      </Select>
      {custom && (
        <Input
          disabled={isLoading}
          value={value}
          label={"Source (nowe źródło — zostanie utworzone przy zapisie)"}
          onChange={formik.handleChange}
          id={"source"}
          name={"source"}
          type={"text"}
        />
      )}
    </>
  );
};

// Editor-level author detection: finds the document's most recent analysis
// run (GET /analysis_runs?doc_id=, sorted newest-first) and asks the LLM to
// extract a byline from the head+tail of the full document text (no
// chunk_ids — the per-chunk variant lives in chunks.tsx, where a reviewer
// can point at one specific chunk instead). Only shown for document types
// that go through chunk analysis; link documents have no full text to run it on.
// Webpages expose document-level extraction in ArticlePreparationPanel; it
// must not depend on an analysis run. This legacy run-backed button remains
// useful for transcripts.
const AUTHOR_EXTRACT_TYPES = ["youtube", "movie", "email"];

const AuthorExtractButton = ({
  formik, isLoading, apiUrl, apiKey,
}: { formik: any; isLoading: boolean; apiUrl?: string; apiKey?: string }) => {
  const [busy, setBusy] = React.useState(false);
  const [status, setStatus] = React.useState<string | null>(null);

  if (!AUTHOR_EXTRACT_TYPES.includes(formik.values.document_type)) return null;

  const handleClick = async () => {
    if (!formik.values.id) return;
    setBusy(true);
    setStatus(null);
    const headers = { "x-api-key": `${apiKey}` };
    try {
      const runsRes = await axios.get(`${apiUrl}/analysis_runs`, {
        headers, params: { doc_id: formik.values.id },
      });
      const runs = runsRes.data.runs ?? [];
      if (runs.length === 0) {
        setStatus("Brak analizy chunków dla tego dokumentu — najpierw ją uruchom.");
        return;
      }
      const res = await axios.post(`${apiUrl}/analysis_run/${runs[0].id}/extract_author`, {}, { headers });
      if (res.data.byline) {
        formik.setFieldValue("byline", res.data.byline);
        setStatus(`Ustawiono autora: ${res.data.byline}`);
      } else {
        setStatus("Nie udało się rozpoznać autora.");
      }
    } catch {
      setStatus("Błąd podczas pobierania autora.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <span style={{ marginLeft: "10px", display: "inline-flex", alignItems: "center", gap: "8px" }}>
      <button
        type="button"
        disabled={isLoading || busy || !formik.values.id}
        className={"button"}
        onClick={handleClick}
      >
        {busy ? "Pobieram…" : "✍️ Pobierz autora"}
      </button>
      {status && <span style={{ fontSize: "0.85em" }}>{status}</span>}
    </span>
  );
};

const SharedInputs = ({
  formik,
  isLoading,
  handleGetLinkByID,
  handleGetEntryToReview,
  handleGetPageByUrl,
}: SharedInputsProps) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [tagSuggestions, setTagSuggestions] = React.useState<string[]>([]);
  const [sourceSuggestions, setSourceSuggestions] = React.useState<string[]>([]);

  React.useEffect(() => {
    const headers = { "x-api-key": `${apiKey}` };
    axios.get(`${apiUrl}/tags`, { headers })
      .then((r) => setTagSuggestions((r.data.tags ?? []).map((t: any) => t.tag)))
      .catch(() => undefined);
    axios.get(`${apiUrl}/sources?active=1`, { headers })
      .then((r) => setSourceSuggestions((r.data.sources ?? []).map((s: any) => s.name ?? s.source)))
      .catch(() => undefined);
  }, [apiUrl, apiKey]);

  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end" }}>
        <div className="flex-grow">
          <Input
            disabled={isLoading}
            value={formik.values.byline}
            label={"Author"}
            onChange={formik.handleChange}
            id={"byline"}
            name={"byline"}
            type={"text"}
          />
        </div>
        <AuthorExtractButton formik={formik} isLoading={isLoading} apiUrl={apiUrl} apiKey={apiKey} />
      </div>
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
            className={"button"}
            style={{ marginTop: "13px", marginLeft: "10px" }}
          >
            ({formik.values.previous_id}) previous
          </NavLink>
        )}
        {formik.values.next_id && formik.values.next_type && (
          <NavLink
            to={`/${formik.values.next_type}/${formik.values.next_id}`}
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
      <SourceSelect formik={formik} isLoading={isLoading} sources={sourceSuggestions} />
      <LanguageSelect formik={formik} isLoading={isLoading} />
      {formik.values.processing_error_code && (
        <div>
          <p style={{ marginBottom: "10px", fontSize: "15px" }}>
            Document state error: {formik.values.processing_error_code}
          </p>
        </div>
      )}
      <Select
        disabled={isLoading}
        value={formik.values.processing_status}
        label={"Document state"}
        onChange={formik.handleChange}
        id={"processing_status"}
        name={"processing_status"}
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
      <TagsInput
        disabled={isLoading}
        value={formik.values.tags ?? ""}
        label={"Tags"}
        suggestions={tagSuggestions}
        onChange={(csv) => formik.setFieldValue("tags", csv)}
      />
    </>
  );
};

export default SharedInputs;
