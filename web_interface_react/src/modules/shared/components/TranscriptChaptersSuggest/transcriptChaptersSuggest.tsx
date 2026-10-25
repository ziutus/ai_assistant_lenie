import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../../context/authorizationContext";
import { ModelOption, modelOptionText } from "../../utils/modelDetails";

type Candidates = { estimated_tokens: number; fits_single_call: boolean | null; model_calls: number | null };
type Chapter = { start_sentence: number; title: string; preview: string; checked: boolean };
type Option = ModelOption & { candidates?: Candidates };

export default function TranscriptChaptersSuggest({ docId, onSaved, disabled = false, onBusyChange }: {
  docId: string; onSaved: () => Promise<unknown>; disabled?: boolean; onBusyChange?: (busy: boolean) => void;
}) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [models, setModels] = React.useState<Option[]>([]);
  const [model, setModel] = React.useState("");
  const [candidates, setCandidates] = React.useState<Candidates>();
  const [chapters, setChapters] = React.useState<Chapter[]>([]);
  const [hash, setHash] = React.useState<string>();
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [cost, setCost] = React.useState("");
  React.useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);
  const config = { headers: { "x-api-key": `${apiKey}` }, timeout: 240000 };
  const selected = models.find(item => item.id === model);
  const plan = selected?.candidates;
  const fits = plan ? plan.fits_single_call : (selected?.context_length && candidates
    ? candidates.estimated_tokens <= selected.context_length * 0.7 : null);
  const calls = plan?.model_calls ?? (selected?.context_length && candidates
    ? Math.ceil(candidates.estimated_tokens / (selected.context_length * 0.7 * 0.9)) : null);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setMessage("");
    try { await action(); }
    catch (error: any) { setMessage(error.response?.data?.message || error.response?.data?.error_code || error.message); }
    finally { setBusy(false); }
  };
  const prepare = () => run(async () => {
    const { data } = await axios.post(`${apiUrl}/document/${docId}/suggest_chapters`, { dry_run: true }, config);
    setModels(data.models); setModel(data.default_model); setCandidates(data.candidates);
  });
  const saveDefault = (value: string | null) => run(async () => {
    const { data } = await axios.put(`${apiUrl}/transcript_chapters/model`, { model: value }, config);
    setModel(data.default_model); setMessage(value ? "Zapisano model domyślny." : "Przywrócono domyślny model serwera.");
  });
  const propose = () => run(async () => {
    setChapters([]); setCost(""); setHash(undefined);
    const { data } = await axios.post(`${apiUrl}/document/${docId}/suggest_chapters`, { model }, config);
    if (data.status === "error") throw new Error(data.error_code);
    setChapters(data.chapters.map((item: Omit<Chapter, "checked">) => ({ ...item, checked: true })));
    setHash(data.text_sha256);
    setCost(`${data.model} · ${data.model_calls} wywołań · ${data.usage.tokens ?? "?"} tokenów · koszt: ${data.usage.cost ?? "nieznany"} ${data.usage.currency ?? ""}`);
  });
  const save = () => run(async () => {
    await axios.post(`${apiUrl}/document/${docId}/apply_chapters`, {
      chapters: chapters.filter(item => item.checked).map(({ start_sentence, title }) => ({ start_sentence, title })),
      expected_text_sha256: hash,
    }, config);
    await onSaved(); setChapters([]); setMessage("Zapisano rozdziały.");
  });
  const locked = busy || disabled;
  return <section style={{ marginBottom: 14, padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc" }}>
    <strong>Podział na rozdziały (AI)</strong>
    <p>Model proponuje tytuły i miejsca podziału. Treść transkrypcji pozostaje bez zmian.</p>
    <button type="button" className="button" disabled={locked} onClick={prepare}>Wybierz model i zaproponuj rozdziały</button>
    {models.length > 0 && <div style={{ marginTop: 10 }}>
      <label>Model <select value={model} disabled={locked} onChange={event => setModel(event.target.value)}>
        {models.map(item => <option key={item.id} value={item.id}>{modelOptionText(item)}</option>)}
      </select></label>
      <p>{fits === null ? "Brak informacji o oknie modelu — nie można zaplanować wywołania."
        : fits ? "Transkrypcja mieści się w całości (1 wywołanie)." : `Transkrypcja wymaga podziału na okna (${calls} wywołań).`}</p>
      {selected?.external && <p role="note" style={{ color: "#92400e" }}>
        ⚠ Ten model wysyła tekst transkrypcji do zewnętrznego pośrednika (OpenRouter).
      </p>}
      <button type="button" disabled={locked} onClick={() => saveDefault(model)}>Ustaw jako domyślny</button>{" "}
      <button type="button" disabled={locked} onClick={() => saveDefault(null)}>Przywróć domyślny serwera</button>{" "}
      <button type="button" className="button" disabled={locked || fits === null} onClick={propose}>Zaproponuj rozdziały</button>
    </div>}
    {chapters.map((chapter, index) => <div key={chapter.start_sentence} style={{ marginTop: 10 }}>
      <input type="checkbox" aria-label={`Zapisz rozdział ${index + 1}`} checked={chapter.checked} disabled={locked}
        onChange={event => setChapters(items => items.map((item, i) => i === index ? { ...item, checked: event.target.checked } : item))} />
      <input aria-label={`Tytuł rozdziału ${index + 1}`} value={chapter.title} maxLength={200} disabled={locked}
        onChange={event => setChapters(items => items.map((item, i) => i === index ? { ...item, title: event.target.value } : item))} />
      <p>{chapter.preview}</p>
    </div>)}
    {cost && <p>{cost}</p>}
    {chapters.length > 0 && <>
      <p>Pierwszy wybrany rozdział obejmie transkrypcję od początku.</p>
      <button type="button" className="button" disabled={locked || !chapters.some(c => c.checked) || chapters.some(c => c.checked && !c.title.trim())}
        onClick={save}>Zapisz rozdziały</button>
    </>}
    {busy && <p role="status">Przetwarzam…</p>}
    {message && <p role="status">{message}</p>}
    <p style={{ color: "#475569" }}>Alternatywa bez wywołań API z UI: w sesji Claude Code uruchom skill /lenie-youtube-outline {docId} - model sesji przygotuje spis treści (outline_md) i kotwice chunków (outline_anchors) bez dodatkowych kosztów. To nie wstawia nagłówków rozdziałów do transkrypcji, tylko steruje podziałem na chunki.</p>
  </section>;
}
