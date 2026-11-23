import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";
import { isModelUnavailable, ModelOption, modelOptionText } from "../../utils/modelDetails";
import { describeRequestError, RequestErrorInfo } from "../../utils/requestError";
import CollapsibleSection from "../CollapsibleSection/collapsibleSection";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";

type Counters = Record<string, number>;
type Usage = { tokens?: number; cost?: string | number; currency?: string } | null;
type KnownRejected = { word: string; count: number; context: string; chapter: number; memory_id: number };
type Preview = {
  suspects: { word: string; count: number; context?: string; chapter?: number; status?: "new" | "memory" | "rejected" }[];
  skipped: Counters; skipped_chapters?: Counters; to_model?: number; from_memory?: number;
};
type Proposal = {
  original: string; replacement: string; confidence: "high" | "medium" | "low"; count: number; context: string;
  chapter?: number; chapter_title?: string; source?: "model" | "memory"; trusted?: boolean;
  memory_documents?: number; memory_id?: number;
};
type Result = {
  proposals: Proposal[]; suspects: number; skipped: Counters; rejected: Counters; skipped_chapters?: Counters;
  from_memory?: number; known_rejected?: KnownRejected[]; model?: string; model_calls?: number; usage: Usage;
};
type Reanalysis = {
  results: ({
    original: string; replacement: string | null; confidence?: Proposal["confidence"]; reason?: string | null;
    context?: string; changed?: boolean; rejected?: string;
  } | null)[];
  rejected: Counters; model?: string; model_calls?: number; usage: Usage; context_chars: number;
};
// `edited`: the reviewer typed the replacement, a re-analysis must not overwrite it (it is offered as `suggestion`).
type Row = Proposal & {
  checked: boolean; applied: boolean; edited?: boolean; reason?: string | null; suggestion?: string; note?: string;
};
type ModelSettings = { default_model: string | null; saved: boolean; models: ModelOption[] };
const skippedLabels: Record<string, string> = {
  capitalized: "wielkie litery", fillers: "wypełniacze", short: "krótkie", repeated: "powtarzane", over_limit: "ponad limit",
};
const chapterTypeLabels: Record<string, string> = { REKLAMA: "reklama", SZUM: "szum", ZRODLA: "źródła" };
const rejectedLabels: Record<string, string> = {
  unchanged: "bez zmiany", unknown_word: "wymyślone słowo", too_different: "zbyt różne od oryginału",
  not_words: "nie są słowami", no_proposal: "brak propozycji", missing_answer: "brak odpowiedzi", unparseable_answer: "nieczytelna odpowiedź",
  not_found: "nie ma już w tekście",
};
// Context (characters on each side of the word) of the successive re-analyses; mirrors the server's steps.
const CONTEXT_STEPS = [400, 900, 1800];
const total = (counts: Counters) => Object.values(counts).reduce((sum, count) => sum + count, 0);
const chapterLabel = (chapter?: number, title?: string) =>
  chapter === undefined ? "" : chapter === 0 ? "wstęp" : `rozdz. ${chapter}${title ? ` „${title}”` : ""}`;
const costText = (usage: Usage) => `${usage?.tokens ?? "?"} tokenów · koszt: ${usage?.cost ?? "nieznany"} ${usage?.currency ?? "?"}`;

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
  const [knownRejected, setKnownRejected] = React.useState<KnownRejected[]>([]);
  const [level, setLevel] = React.useState(0); // how many re-analyses were done: the next one reads a larger context
  const [busy, setBusy] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo>();
  const [message, setMessage] = React.useState("");
  const config = { headers: { "x-api-key": `${apiKey}` }, timeout: 240000 };
  const endpoint = `${apiUrl}/document/${docId}/transcript_spellcheck`;
  const selected = models.find(item => item.id === model);
  const modelBlocked = !!selected && isModelUnavailable(selected);
  const checked = rows.filter(row => row.checked && !row.applied);
  const invalid = !checked.length || checked.some(row => !row.replacement.trim());
  // A pair the reviewer already confirmed in several documents needs no second opinion from the model.
  const reanalysable = rows.filter(row => !row.applied && !(row.source === "memory" && row.trusted));
  const nextContext = CONTEXT_STEPS[Math.min(level, CONTEXT_STEPS.length - 1)];
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
  // The reviewer's decisions feed the per-channel memory (no model call for the same word next time). Never throws:
  // a failed save must not hide that the text was already changed.
  const remember = async (decisions: { original: string; decision: "accepted" | "rejected"; replacement?: string }[]) => {
    if (!decisions.length) return true;
    try {
      await axios.post(`${endpoint}/decisions`, { decisions }, config);
      return true;
    } catch (cause) { console.error(cause); return false; }
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
    setLevel(0);
    setKnownRejected(data.known_rejected ?? []);
    // One list for the whole transcript, ordered by chapter (the sort is stable, so the server order holds inside one).
    setRows(data.proposals.filter(row => !dismissed.current.has(row.original))
      .map(row => ({ ...row, checked: row.source === "memory" && row.trusted === true, applied: false }))
      .sort((a, b) => (a.chapter ?? 0) - (b.chapter ?? 0)));
  });
  const reanalyse = () => run("Nie udało się przeanalizować ponownie", async () => {
    const items = reanalysable;
    const { data } = await axios.post<Reanalysis>(`${endpoint}/reanalyze`, {
      items: items.map(row => ({ original: row.original, replacement: row.replacement || null, chapter: row.chapter ?? null })),
      context_chars: nextContext, ...(model ? { model } : {}),
    }, config);
    // The panel is locked while this runs, so `rows` cannot change under the answer; computed outside the state updater
    // so that the counter is not doubled by a re-run of the updater.
    let changed = 0;
    const next = rows.map(row => {
      const index = items.indexOf(row);
      const answer = index === -1 ? null : data.results[index];
      if (!answer) return row;
      // A longer context is useful on its own, even when the model keeps or cannot improve the proposal.
      const base = { ...row, context: answer.context ?? row.context };
      if (!answer.replacement) {
        return { ...base, note: `Model nie zmienił propozycji${answer.rejected ? ` (${rejectedLabels[answer.rejected] ?? answer.rejected})` : ""}.` };
      }
      const confidence = answer.confidence ?? row.confidence;
      if (row.edited) {
        return { ...base, confidence, reason: answer.reason, note: undefined,
          suggestion: answer.replacement.toLowerCase() === row.replacement.toLowerCase() ? undefined : answer.replacement };
      }
      if (answer.changed) changed++;
      // A changed proposal has to be read again: it loses its tick.
      return { ...base, replacement: answer.replacement, confidence, reason: answer.reason, suggestion: undefined, note: undefined,
        checked: answer.changed ? false : row.checked };
    });
    setRows(next);
    setLevel(value => value + 1);
    setMessage(`Ponowna analiza (±${data.context_chars} znaków kontekstu): ${changed} z ${items.length} poprawek zmienionych · ${data.model ?? "?"} · ${data.model_calls ?? "?"} wywołań · ${costText(data.usage)}`);
  });
  const apply = () => run("Nie udało się zastosować poprawki", async () => {
    const done: Row[] = [];
    let saved = true;
    try {
      for (const row of checked) {
        await axios.post(`${apiUrl}/transcript_corrections/apply`, {
          document_id: Number(docId), dry_run: false, pattern: row.original, replacement: row.replacement,
        }, config);
        done.push(row);
        setRows(items => items.map(item => item === row ? { ...item, checked: false, applied: true } : item));
      }
    } finally {
      if (done.length) {
        saved = await remember(done.map(row => ({ original: row.original, decision: "accepted", replacement: row.replacement })));
        setMessage(`Zastosowano ${done.length} poprawek w tekście. Encje i chunki nie zostały przebudowane — uruchom „Wykryj osoby i miejsca”, jeśli to potrzebne.${saved ? "" : " Nie zapisano decyzji w pamięci kanału."}`);
        onApplied();
      }
    }
  });
  const reject = (index: number) => {
    const row = rows[index];
    dismissed.current.add(row.original);
    setConfirming(false);
    setRows(items => items.filter((_, i) => i !== index));
    // "Odrzuć" means: not a transcription error. The word is remembered for this channel and not sent to the model again.
    void remember([{ original: row.original, decision: "rejected" }]).then(saved => {
      if (!saved) setMessage(`Nie zapisano odrzucenia „${row.original}” w pamięci — słowo może wrócić przy następnym uruchomieniu.`);
    });
  };
  const restore = (item: KnownRejected) => run("Nie udało się przywrócić słowa", async () => {
    await axios.delete(`${apiUrl}/transcript_spellcheck/memory/${item.memory_id}`, config);
    dismissed.current.delete(item.word);
    setKnownRejected(items => items.filter(other => other !== item));
    setMessage(`Przywrócono „${item.word}”. Uruchom „Zaproponuj poprawki” ponownie, żeby je zobaczyć.`);
  });
  const update = (index: number, change: Partial<Row>) => {
    setConfirming(false);
    setRows(items => items.map((item, i) => i === index ? { ...item, ...change } : item));
  };
  const memoryCount = result ? result.proposals.filter(row => row.source === "memory").length : 0;
  return <CollapsibleSection title="Błędy transkrypcji (słownik + model)" onToggle={event => {
    if (event.currentTarget.open && !opened.current) { opened.current = true; void loadModels(); }
  }}>
    <fieldset disabled={busy} style={{ border: 0, padding: 0, minWidth: 0 }}>
      <p>Tekst jest czytany rozdział po rozdziale; rozdziały typu reklama, szum i źródła są pomijane. Słowa, które już oceniałeś
        w tym kanale, wracają z pamięci bez wywołania modelu.</p>
      <p><button type="button" onClick={() => run("Nie udało się znaleźć podejrzanych słów", async () => {
        const { data } = await axios.post<Preview>(endpoint, { dry_run: true }, config);
        setPreview(data);
      })}>Znajdź podejrzane słowa</button></p>
      {preview && <div>
        <p>Słownik uznał za podejrzane: {preview.suspects.length} słów. Pominięto: {total(preview.skipped)}.</p>
        {preview.skipped_chapters && total(preview.skipped_chapters) > 0 && <p>Pominięte rozdziały: {Object.entries(preview.skipped_chapters)
          .map(([type, count]) => `${chapterTypeLabels[type] ?? type}: ${count}`).join(", ")}.</p>}
        {preview.to_model !== undefined && <p>Do modelu trafi: {preview.to_model} · z pamięci: {preview.from_memory ?? 0}
          {" "}· odrzucone wcześniej: {preview.suspects.filter(item => item.status === "rejected").length}.</p>}
        <ul>{Object.entries(preview.skipped).map(([reason, count]) => <li key={reason}>{skippedLabels[reason] ?? reason}: {count}</li>)}</ul>
        {preview.suspects.length ? <ul>{preview.suspects.map(item => <li key={item.word}>{item.word} ×{item.count}{
          item.status === "memory" ? " · z pamięci" : item.status === "rejected" ? " · odrzucone wcześniej" : ""}</li>)}</ul>
          : <p>Nie znaleziono podejrzanych słów.</p>}
      </div>}
      <label>Model <select value={model} onChange={event => setModel(event.target.value)}>
        <option value="">Domyślny model serwera</option>
        {models.map(item => <option key={item.id} value={item.id} disabled={isModelUnavailable(item)}>{modelOptionText(item)}</option>)}
      </select></label>
      {selected?.external && <p role="note">Ten model wysyła tekst transkrypcji do zewnętrznego pośrednika.</p>}
      <p>
        <button type="button" disabled={!model || modelBlocked} onClick={() => saveDefault(model)}>Ustaw jako domyślny</button>{" "}
        <button type="button" onClick={() => saveDefault(null)}>Przywróć domyślny serwera</button>{" "}
        <button type="button" disabled={modelBlocked} onClick={propose}>Zaproponuj poprawki</button>
      </p>
      {result && <>
        <p>Model zaproponował {result.proposals.length - memoryCount} poprawek{memoryCount ? ` · z pamięci: ${memoryCount} (bez modelu)` : ""} · {result.model ?? "?"} · {result.model_calls ?? "?"} wywołań · {costText(result.usage)}</p>
        {result.skipped_chapters && total(result.skipped_chapters) > 0 && <p>Pominięte rozdziały: {Object.entries(result.skipped_chapters)
          .map(([type, count]) => `${chapterTypeLabels[type] ?? type}: ${count}`).join(", ")}.</p>}
        <CollapsibleSection title={`Odrzucone przez walidację (${total(result.rejected)})`}>
          <ul>{Object.entries(result.rejected).map(([reason, count]) => <li key={reason}>{rejectedLabels[reason] ?? reason}: {count}</li>)}</ul>
        </CollapsibleSection>
      </>}
      {knownRejected.length > 0 && <CollapsibleSection title={`Pominięte — odrzucone wcześniej (${knownRejected.length})`}>
        <ul>{knownRejected.map(item => <li key={item.memory_id}>{item.word} ×{item.count}{" "}
          <button type="button" aria-label={`Przywróć słowo ${item.word}`} onClick={() => restore(item)}>Przywróć</button></li>)}</ul>
      </CollapsibleSection>}
      {rows.length > 0 && <>
        <button type="button" onClick={() => { setConfirming(false); setRows(items => items.map(item => item.applied ? item : { ...item, checked: true })); }}>Zaznacz wszystkie</button>{" "}
        <button type="button" onClick={() => { setConfirming(false); setRows(items => items.map(item => ({ ...item, checked: false }))); }}>Odznacz wszystkie</button>{" "}
        <button type="button" disabled={modelBlocked || !reanalysable.length} onClick={reanalyse}
          title="Model czyta dłuższy fragment wokół każdej nieodrzuconej poprawki i podaje, co mówca miał na myśli">
          Przeanalizuj ponownie z większym kontekstem (±{nextContext} znaków)</button>
        {rows.map((row, index) => <div key={row.original} style={{ marginTop: 10 }}>
          {row.applied ? <span>✓ zastosowano </span> : <input type="checkbox" aria-label={`Zastosuj poprawkę dla ${row.original}`}
            checked={row.checked} onChange={event => update(index, { checked: event.target.checked })} />}
          <span>{row.original} → </span>
          <input aria-label={`Poprawka dla ${row.original}`} value={row.replacement} disabled={row.applied}
            onChange={event => update(index, { replacement: event.target.value, edited: true })} />
          <span> ×{row.count} · pewność: {({ high: "wysoka", medium: "średnia", low: "niska" })[row.confidence]}
            {row.chapter !== undefined && <> · {chapterLabel(row.chapter, row.chapter_title)}</>}
            {row.source === "memory" && <> · z pamięci{row.memory_documents ? ` (${row.memory_documents} dok.)` : ""}{row.trusted ? ", sprawdzone" : ""}</>} </span>
          <button type="button" aria-label={`Odrzuć poprawkę dla ${row.original}`} disabled={row.applied}
            title="To nie jest błąd transkrypcji: słowo zostanie zapamiętane i nie będzie ponownie proponowane dla tego kanału"
            onClick={() => reject(index)}>Odrzuć</button>
          {row.reason && <p>Co mówca miał na myśli: {row.reason}</p>}
          {row.suggestion && <p>Model proponuje po ponownej analizie: „{row.suggestion}”{" "}
            <button type="button" aria-label={`Użyj propozycji modelu dla ${row.original}`}
              onClick={() => update(index, { replacement: row.suggestion!, suggestion: undefined, edited: false })}>Użyj</button></p>}
          {row.note && <p>{row.note}</p>}
          <p style={row.context.length > 700 ? { maxHeight: "14em", overflow: "auto" } : undefined}><Context text={row.context} original={row.original} /></p>
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
