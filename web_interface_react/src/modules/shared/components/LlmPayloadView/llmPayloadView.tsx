import React from "react";
import CollapsibleSection from "../CollapsibleSection/collapsibleSection";
import { copyText } from "../../utils/copyText";

export interface LlmPayload {
  system_prompt?: string | null;
  request_text: string | null;
  response_text: string | null;
  error?: string | null;
  request_extra?: unknown;
  request_truncated?: boolean;
  response_truncated?: boolean;
}

function PayloadText({ title, text, copyLabel, empty }: { title: string; text: string | null; copyLabel: string; empty: string }) {
  const [copied, setCopied] = React.useState<boolean | null>(null);
  return <CollapsibleSection title={title}>
    <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 320, overflow: "auto" }}>{text || empty}</pre>
    <button type="button" onClick={async () => setCopied(await copyText(text ?? ""))}>{copyLabel}</button>
    {copied !== null && <span role="status">{copied ? " Skopiowano." : " Nie udało się skopiować — zaznacz tekst ręcznie."}</span>}
  </CollapsibleSection>;
}

export default function LlmPayloadView({ payload, countryDetection = false }: { payload: LlmPayload; countryDetection?: boolean }) {
  return <div>
    {(payload.request_truncated || payload.response_truncated) && <p role="status" style={{ color: "#b45309" }}>Zapis obcięty (limit pola)</p>}
    {payload.error && <p role="alert" style={{ color: "#b91c1c" }}><strong>Błąd:</strong> {payload.error}</p>}
    {payload.system_prompt && <PayloadText title="Prompt systemowy" text={payload.system_prompt} copyLabel="Kopiuj prompt systemowy" empty="(pusty prompt)" />}
    <PayloadText title={countryDetection ? "Pełny prompt" : "Zapytanie"} text={payload.request_text} copyLabel="Kopiuj prompt" empty="(pusty prompt)" />
    <PayloadText title={countryDetection ? "Surowa odpowiedź modelu" : "Odpowiedź modelu"} text={payload.response_text} copyLabel="Kopiuj odpowiedź" empty="(pusta odpowiedź)" />
    {payload.request_extra != null && <PayloadText title="Dodatkowe parametry zapytania" text={JSON.stringify(payload.request_extra, null, 2)} copyLabel="Kopiuj parametry" empty="(brak parametrów)" />}
  </div>;
}
