import React from "react";
import axios from "axios";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";
import { isModelUnavailable, modelOptionText, type ModelOption } from "../../utils/modelDetails";

export interface ChapterModelState {
  models: ModelOption[];
  /** The model that will be sent; "" until the list was loaded or a model was chosen (the server then uses its default). */
  model: string;
  setModel: (value: string) => void;
  defaultModel: string;
  /** true = the household chose the default; false = it is the built-in one. */
  saved: boolean;
  loading: boolean;
  error: RequestErrorInfo | null;
  /** Fetches the allowed models with prices; idempotent, called when the picker is opened. */
  load: () => void;
  saveDefault: (value: string | null) => Promise<void>;
}

/**
 * Model choice for the per-chapter analyses (tone, historical period, dated events): `GET/PUT /chapter_analysis/model`.
 * The list is fetched lazily (when the picker is opened), so a page with many chapters does not ask for it on load.
 */
export const useChapterModel = (apiUrl: string, apiKey: string | undefined): ChapterModelState => {
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);
  const [models, setModels] = React.useState<ModelOption[]>([]);
  const [model, setModel] = React.useState("");
  const [defaultModel, setDefaultModel] = React.useState("");
  const [saved, setSaved] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const requested = React.useRef(false);

  const load = React.useCallback(() => {
    if (requested.current) return;
    requested.current = true;
    setLoading(true);
    const startedAt = Date.now();
    axios.get(`${apiUrl}/chapter_analysis/model`, { headers })
      .then((response) => {
        setModels(Array.isArray(response.data?.models) ? response.data.models : []);
        setDefaultModel(response.data?.default_model ?? "");
        setSaved(Boolean(response.data?.saved));
        setModel((current) => current || response.data?.default_model || "");
      })
      .catch((err) => {
        requested.current = false; // let the next opening try again
        setError(describeRequestError(err, "Pobieranie listy modeli", { startedAt }));
      })
      .finally(() => setLoading(false));
  }, [apiUrl, headers]);

  const saveDefault = React.useCallback(async (value: string | null) => {
    setError(null);
    const startedAt = Date.now();
    try {
      const response = await axios.put(`${apiUrl}/chapter_analysis/model`, { model: value }, { headers });
      setDefaultModel(response.data?.default_model ?? "");
      setSaved(Boolean(response.data?.saved));
      setModel(response.data?.default_model ?? "");
    } catch (err) {
      setError(describeRequestError(err, "Zapis domyślnego modelu", { startedAt }));
    }
  }, [apiUrl, headers]);

  return { models, model, setModel, defaultModel, saved, loading, error, load, saveDefault };
};

interface PickerProps {
  state: ChapterModelState;
  /** Text of the collapsed summary, e.g. "Model". */
  summary?: string;
  disabled?: boolean;
}

/**
 * Collapsed model chooser: every option shows its price per 1 mln tokens and its context window, so a reviewer can
 * weigh a larger or cheaper model against Bielik (the built-in default) before running an analysis.
 */
const ChapterModelPicker: React.FC<PickerProps> = ({ state, summary = "Model", disabled }) => {
  const { models, model, setModel, defaultModel, saved, loading, error, load, saveDefault } = state;
  const current = models.find((option) => option.id === model);
  return (
    <details onToggle={(event) => { if ((event.currentTarget as HTMLDetailsElement).open) load(); }} style={{ margin: "4px 0" }}>
      <summary style={{ cursor: "pointer", fontSize: "0.85em" }}>
        {summary}: {current ? current.label : model || "domyślny"}
      </summary>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginTop: 4 }}>
        <select
          aria-label="Model do analizy rozdziału"
          value={model}
          onChange={(event) => setModel(event.target.value)}
          disabled={disabled || loading || models.length === 0}
          style={{ maxWidth: "100%" }}
        >
          {models.length === 0 && <option value="">{loading ? "Ładuję modele…" : "Model domyślny serwera"}</option>}
          {models.map((option) => (
            <option key={option.id} value={option.id} disabled={isModelUnavailable(option)}>
              {modelOptionText(option)}{option.id === defaultModel ? " — domyślny" : ""}
            </option>
          ))}
        </select>
        <button type="button" disabled={disabled || !model || (model === defaultModel && saved)} onClick={() => void saveDefault(model)}>
          Ustaw jako domyślny
        </button>
        {saved && <button type="button" disabled={disabled} onClick={() => void saveDefault(null)}>Przywróć domyślny serwera</button>}
      </div>
      {current?.external && (
        <small style={{ color: "#b45309" }}>⚠ Zewnętrzny dostawca: tekst rozdziału zostanie do niego wysłany.</small>
      )}
      {error && (
        <div role="alert" style={{ color: "#a33" }}>
          <p>{error.summary}</p>
          <RequestErrorDetails details={error.details} />
        </div>
      )}
    </details>
  );
};

export default ChapterModelPicker;
