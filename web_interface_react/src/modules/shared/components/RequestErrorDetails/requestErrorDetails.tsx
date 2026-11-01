import React from "react";
import { copyText } from "../../utils/copyText";

/**
 * "Szczegóły techniczne" disclosure shown under an error message: the text from
 * `describeRequestError().details` plus a copy button, so the user can paste it
 * into a bug report instead of describing what happened from memory.
 */
const RequestErrorDetails: React.FC<{ details: string }> = ({ details }) => {
  const [copied, setCopied] = React.useState<boolean | null>(null);
  if (!details) return null;
  return (
    <details style={{ marginTop: "4px", color: "#556" }}>
      <summary style={{ cursor: "pointer" }}>Szczegóły techniczne</summary>
      <pre style={{ whiteSpace: "pre-wrap", margin: "4px 0", fontSize: "0.85em" }}>{details}</pre>
      <button
        type="button"
        onClick={async () => setCopied(await copyText(details))}
      >
        Kopiuj szczegóły
      </button>
      {copied === true && <span style={{ marginLeft: "6px" }}>Skopiowano.</span>}
      {copied === false && <span style={{ marginLeft: "6px", color: "#a33" }}>Nie udało się skopiować — zaznacz tekst ręcznie.</span>}
    </details>
  );
};

export default RequestErrorDetails;
