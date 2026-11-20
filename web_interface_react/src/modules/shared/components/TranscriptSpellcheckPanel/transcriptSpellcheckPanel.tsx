import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";
import { isModelUnavailable, ModelOption, modelOptionText } from "../../utils/modelDetails";
import { describeRequestError, RequestErrorInfo } from "../../utils/requestError";
import CollapsibleSection from "../CollapsibleSection/collapsibleSection";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";

type Counters = Record<string, number>;
type Preview = { suspects: { word: string; count: number; context: string }[]; skipped: Counters };
type Proposal = { original: string; replacement: string; confidence: "high" | "medium" | "low"; count: number; context: string };
type Result = {
  proposals: Proposal[]; suspects: number; skipped: Counters; rejected: Counters;
  model?: string; model_calls?: number;
  usage: { tokens?: number; cost?: string | number; currency?: string } | null;
};
type Row = Proposal & { checked: boolean; applied: boolean };
type ModelSettings = { default_model: string | null; saved: boolean; models: ModelOption[] };
const skippedLabels: Record<string, string> = {
  capitalized: "wielkie litery", fillers: "wypełniacze", short: "krótkie", repeated: "powtarzane", over_limit: "ponad limit",
};
const rejectedLabels: Record<string, string> = {
  unchanged: "bez zmiany", unknown_word: "wymyślone słowo", too_different: "zbyt różne od oryginału",
  not_words: "nie są słowami", no_proposal: "brak propozycji", missing_answer: "brak odpowiedzi", unparseable_answer: "nieczytelna odpowiedź",
};
const total = (counts: Counters) => Object.values(counts).reduce((sum, count) => sum + count, 0);

function Context({ text, original }: { text: string; original: string }) {
  if (!original) return <>{text}</>;
  const escaped = original.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return <>{text.split(new RegExp(`(${escaped})`, "gi")).map((part, index) =>
    index % 2 ? <mark key={index}>{part}</mark> : part)}</>;
}

export default function TranscriptSpellcheckPanel({ docId, onApplied }: { docId: string; onApplied: () => void }) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const opened = React.useRef(false);
  const running = React.useRef(false);
  const dismissed = React.useRef(new Set<string>());
  const [models, setModels] = React.useState<ModelOption[]>([]);
  const [model, setModel] = React.useState("");
  const [preview, setPreview] = React.useState<Preview>();
  const [result, setResult] = React.useState<Result>();
  const [rows, setRows] = React.useState<Row[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo>();
  const [message, setMessage] = React.useState("");
  const config = { headers: { "x-api-key": `${apiKey}` }, timeout: 240000 };
  const endpoint = `${apiUrl}/document/${docId}/transcript_spellcheck`;
  const selected = models.find(item => item.id === model);
  const checked = rows.filter(row => row.checked && !row.applied);
  const invalid = !checked.length || checked.some(row => !row.replacement.trim());
  const run = async (operation: string, action: () => Promise<void>) => {
    if (running.current) return;
    running.current = true;
    setBusy(true); setError(undefined); setMessage(""); setConfirming(false);
    const startedAt = Date.now();
    try { await action(); }
    catch (cause) {
      console.error(cause);
      setError(describeRequestError(cause, operation, { startedAt, context: { Dokument: docId } }));
    } finally { running.current = false; setBusy(false); }
  };
  const settings = (data: ModelSettings) => { setModels(data.models); setModel(data.default_model ?? ""); };
  const loadModels = () => run("Nie udało się pobrać modeli", async () => {
    const { data } = await axios.get<ModelSettings>(`${apiUrl}/transcript_spellcheck/model`, config);
    settings(data);
  });
  const saveDefault = (value: string | null) => run("Nie udało się zapisać modelu domyślnego", async () => {
    const { data } = await axios.put<ModelSettings>(`${apiUrl}/transcript_spellcheck/model`, { model: value }, config);
    settings(data);
    setMessage(value ? "Zapisano model domyślny." : "Przywrócono domyślny model serwera.");
  });
  const propose = () => run("Nie udało się zaproponować poprawek", async () => {
    const { data } = await axios.post<Result>(endpoint, model ? { model } : {}, config);
    setResult(data);
    setRows(data.proposals.filter(row => !dismissed.current.has(row.original))
      .map(row => ({ ...row, checked: false, applied: false })));
  });
  const apply = () => run("Nie udało się zastosować poprawki", async () => {
    let applied = 0;
    try {
      for (const row of checked) {
        await axios.post(`${apiUrl}/transcript_corrections/apply`, {
          document_id: Number(docId), dry_run: false, pattern: row.original, replacement: row.replacement,
        }, config);
        applied++;
        setRows(items => items.map(item => item === row ? { ...item, checked: false, applied: true } : item));
      }
    } finally {
      if (applied) {
        setMessage(`Zastosowano ${applied} poprawek w tekście. Encje i chunki nie zostały przebudowane — uruchom „Wykryj osoby i miejsca”, jeśli to potrzebne.`);
        onApplied();
      }
    }
  });
  const update = (index: number, change: Partial<Row>) => {
    setConfirming(false);
    setRows(items => items.map((item, i) => i === index ? { ...item, ...change } : item));
  };
  return <CollapsibleSection title="Błędy transkrypcji (słownik + model)" onToggle={event => {
    if (event.currentTarget.open && !opened.current) { opened.current = true; void loadModels(); }
  }}>
    <fieldset disabled={busy} style={{ border: 0, padding: 0, minWidth: 0 }}>
      <p><button type="button" onClick={() => run("Nie udało się znaleźć podejrzanych słów", async () => {
        const { data } = await axios.post<Preview>(endpoint, { dry_run: true }, config);
        setPreview(data);
      })}>Znajdź podejrzane słowa</button></p>
      {preview && <div>
        <p>Słownik uznał za podejrzane: {preview.suspects.length} słów. Pominięto: {total(preview.skipped)}.</p>
        <ul>{Object.entries(preview.skipped).map(([reason, count]) => <li key={reason}>{skippedLabels[reason] ?? reason}: {count}</li>)}</ul>
        {preview.suspects.length ? <ul>{preview.suspects.map(item => <li key={item.word}>{item.word} ×{item.count}</li>)}</ul>
          : <p>Nie znaleziono podejrzanych słów.</p>}
      </div>}
      <label>Model <select value={model} onChange={event => setModel(event.target.value)}>
        <option value="">Domyślny model serwera</option>
        {models.map(item => <option key={item.id} value={item.id} disabled={isModelUnavailable(item)}>{modelOptionText(item)}</option>)}
      </select></label>
      {selected?.external && <p role="note">Ten model wysyła tekst transkrypcji do zewnętrznego pośrednika.</p>}
      <p>
        <button type="button" disabled={!model || (selected && isModelUnavailable(selected))} onClick={() => saveDefault(model)}>Ustaw jako domyślny</button>{" "}
        <button type="button" onClick={() => saveDefault(null)}>Przywróć domyślny serwera</button>{" "}
        <button type="button" disabled={selected && isModelUnavailable(selected)} onClick={propose}>Zaproponuj poprawki</button>
      </p>
      {result && <>
        <p>Model zaproponował {result.proposals.length} poprawek · {result.model ?? "?"} · {result.model_calls ?? "?"} wywołań · {result.usage?.tokens ?? "?"} tokenów · koszt: {result.usage?.cost ?? "nieznany"} {result.usage?.currency ?? "?"}</p>
        <CollapsibleSection title={`Odrzucone przez walidację (${total(result.rejected)})`}>
          <ul>{Object.entries(result.rejected).map(([reason, count]) => <li key={reason}>{rejectedLabels[reason] ?? reason}: {count}</li>)}</ul>
        </CollapsibleSection>
      </>}
      {rows.length > 0 && <>
        <button type="button" onClick={() => { setConfirming(false); setRows(items => items.map(item => item.applied ? item : { ...item, checked: true })); }}>Zaznacz wszystkie</button>{" "}
        <button type="button" onClick={() => { setConfirming(false); setRows(items => items.map(item => ({ ...item, checked: false }))); }}>Odznacz wszystkie</button>
        {rows.map((row, index) => <div key={index} style={{ marginTop: 10 }}>
          {row.applied ? <span>✓ zastosowano </span> : <input type="checkbox" aria-label={`Zastosuj poprawkę dla ${row.original}`}
            checked={row.checked} onChange={event => update(index, { checked: event.target.checked })} />}
          <span>{row.original} → </span>
          <input aria-label={`Poprawka dla ${row.original}`} value={row.replacement} disabled={row.applied}
            onChange={event => update(index, { replacement: event.target.value })} />
          <span> ×{row.count} · pewność: {({ high: "wysoka", medium: "średnia", low: "niska" })[row.confidence]} </span>
          <button type="button" aria-label={`Odrzuć poprawkę dla ${row.original}`} disabled={row.applied} onClick={() => {
            dismissed.current.add(row.original); setConfirming(false); setRows(items => items.filter((_, i) => i !== index));
          }}>Odrzuć</button>
          <p><Context text={row.context} original={row.original} /></p>
        </div>)}
        <button type="button" disabled={invalid} onClick={() => setConfirming(true)}>Zastosuj zaznaczone ({checked.length})</button>
        {confirming && <div>
          <p>Zmienię tekst dokumentu: {checked.length} poprawek. Tego nie cofnie się jednym kliknięciem.</p>
          <button type="button" disabled={invalid} onClick={apply}>Potwierdź</button>{" "}
          <button type="button" onClick={() => setConfirming(false)}>Anuluj</button>
        </div>}
      </>}
      {error && <div role="alert"><p>{error.summary}</p><RequestErrorDetails details={error.details} /></div>}
    </fieldset>
    {busy && <p role="status">Przetwarzam…</p>}
    {message && <p role="status">{message}</p>}
  </CollapsibleSection>;
}
