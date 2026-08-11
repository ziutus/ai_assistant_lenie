import React from "react";
import { useFormik } from "formik";
import { useManageLLM } from "../hooks/useManageLLM";
import SharedInputs from "../components/SharedInputs/sharedInputs";
import InputsForAllExceptLink from "../components/SharedInputs/InputsForAllExceptLink";
import { useParams } from "react-router-dom";
import FormButtons from "../components/FormButtons/formButtons";
import Input from "../components/Input/input";
import { AuthorizationContext } from '../context/authorizationContext';

const Email = () => {
  const { id } = useParams();
  const { selectedDocumentType, selectedDocumentState} = React.useContext(AuthorizationContext);
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [footerMessage, setFooterMessage] = React.useState("");
  const [footerBusy, setFooterBusy] = React.useState(false);
  const [savedFooter, setSavedFooter] = React.useState<string | null>(null);
  const [footerLoaded, setFooterLoaded] = React.useState(false);

  React.useEffect(() => {
    if (id) {
      handleGetLinkByID(id).then(() => null);
    }
  }, [id]);

  const formik: any = useFormik({
    initialValues: {
      id: "",
      byline: "",
      email_sender: "",
      source: "",
      language: "",
      url: "",
      tags: "",
      title: "",
      document_type: "email",
      summary: "",
      text: "",
      text_md: "",
      processing_status: "",
      processing_error_code: "",
      chapter_list: "",
      note: "",
      next_id: null,
      previous_id: null,
      next_type: "",
      previous_type: "",
    },
    onSubmit: () => {},
  });

  const {
    message,
    isError,
    isLoading,
    handleGetPageByUrl,
    handleSaveWebsiteNext,
    handleSaveWebsiteToCorrect,
    handleGetLinkByID,
    handleGetEntryToReview,
    handleRemoveNotNeededText
  } = useManageLLM({
    formik, selectedDocumentType, selectedDocumentState
  });

  React.useEffect(() => {
    if (!formik.values.id || !formik.values.email_sender) {
      setSavedFooter(null);
      setFooterLoaded(false);
      return;
    }

    let active = true;
    fetch(`${apiUrl}/document/${formik.values.id}/email_footer_rule`, {
      headers: { "x-api-key": apiKey ?? "" },
    })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || "Nie udało się pobrać reguły stopki.");
        if (active) setSavedFooter(data.footer_text || null);
      })
      .catch(() => {
        if (active) setSavedFooter(null);
      })
      .finally(() => {
        if (active) setFooterLoaded(true);
      });

    return () => {
      active = false;
    };
  }, [apiKey, apiUrl, formik.values.email_sender, formik.values.id]);

  const markSelectedFooter = async () => {
    const textArea = document.getElementById("text") as HTMLTextAreaElement | null;
    const footerText = textArea?.value.slice(textArea.selectionStart, textArea.selectionEnd) || "";
    if (!formik.values.id || !footerText.trim()) {
      setFooterMessage("Zaznacz końcowy fragment stopki w treści e-maila.");
      return;
    }
    setFooterBusy(true);
    try {
      const response = await fetch(`${apiUrl}/document/${formik.values.id}/email_footer_rule`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": apiKey ?? "" },
        body: JSON.stringify({ email_sender: formik.values.email_sender, footer_text: footerText }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Nie udało się zapisać reguły.");
      formik.setFieldValue("email_sender", data.email_sender);
      formik.setFieldValue("text", data.text);
      setSavedFooter(footerText.trim());
      setFooterLoaded(true);
      setFooterMessage("Stopka usunięta i zapisana dla kolejnych e-maili od tego nadawcy.");
    } catch (error: any) {
      setFooterMessage(error.message || "Nie udało się zapisać reguły.");
    } finally {
      setFooterBusy(false);
    }
  };

  const removeFooterRule = async () => {
    if (!formik.values.id) return;
    setFooterBusy(true);
    try {
      const response = await fetch(`${apiUrl}/document/${formik.values.id}/email_footer_rule`, {
        method: "DELETE",
        headers: { "x-api-key": apiKey ?? "" },
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Nie udało się usunąć reguły.");
      setSavedFooter(null);
      setFooterLoaded(true);
      setFooterMessage("Reguła stopki dla tego nadawcy została usunięta.");
    } catch (error: any) {
      setFooterMessage(error.message || "Nie udało się usunąć reguły.");
    } finally {
      setFooterBusy(false);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Email</h2>
      <form onSubmit={formik.handleSubmit} style={{ maxWidth: "800px" }}>
        <SharedInputs
          formik={formik}
          isLoading={isLoading}
          handleGetLinkByID={(id: any) => handleGetLinkByID(id, true)}
          handleGetEntryToReview={handleGetEntryToReview}
          handleGetPageByUrl={handleGetPageByUrl}
        />
        <Input
          disabled={isLoading}
          value={formik.values.email_sender}
          label="Adres nadawcy"
          onChange={formik.handleChange}
          id="email_sender"
          name="email_sender"
          type="email"
        />
        <InputsForAllExceptLink
          formik={formik}
          isLoading={isLoading}
          handleRemoveNotNeededText={handleRemoveNotNeededText}
        />
        {formik.values.id && (
          <section style={{ margin: "12px 0", padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc" }}>
            <strong>Stopka e-maila</strong>
            <p style={{ margin: "5px 0 10px", color: "#475569" }}>
              Zaznacz końcowy fragment w polu treści. Reguła będzie działała tylko dla tego adresu nadawcy.
            </p>
            {footerLoaded && (
              savedFooter ? (
                <div style={{ margin: "0 0 10px" }}>
                  <span style={{ color: "#475569" }}>Aktualnie zapisana stopka dla tego nadawcy:</span>
                  <pre style={{ margin: "5px 0 0", padding: 8, whiteSpace: "pre-wrap", background: "#fff", border: "1px solid #cbd5e1", borderRadius: 4 }}>
                    {savedFooter}
                  </pre>
                </div>
              ) : (
                <p style={{ margin: "0 0 10px", color: "#475569" }}>Brak zapisanej stopki dla tego nadawcy.</p>
              )
            )}
            <button type="button" className="button" onClick={markSelectedFooter} disabled={isLoading || footerBusy}>
              {footerBusy ? "Zapisuję…" : "Oznacz zaznaczenie jako stopkę"}
            </button>
            <button type="button" className="button" style={{ marginLeft: 8 }} onClick={removeFooterRule} disabled={isLoading || footerBusy}>
              Usuń regułę stopki
            </button>
            {footerMessage && <p style={{ margin: "8px 0 0" }}>{footerMessage}</p>}
          </section>
        )}

        <FormButtons
          message={message}
          formik={formik}
          isError={isError}
          isLoading={isLoading}
          handleSaveWebsiteNext={handleSaveWebsiteNext}
          handleSaveWebsiteToCorrect={handleSaveWebsiteToCorrect}
        />
      </form>
    </div>
  );
};

export default Email;
