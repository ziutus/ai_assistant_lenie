import React from "react";
import axios from "axios";

export interface PhotoDescription {
  text: string;
  model: string;
  generated_at: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
}

export interface ContactPhotoData {
  id?: string;
  subject_kind?: "people" | "no_people" | "unknown";
  people_count?: number | null;
  classification_revision?: number;
  depicts_contact?: boolean | null;
  link_revision?: number;
  storage_key: string;
  user_description: string | null;
  user_description_revision: number;
  ai_descriptions: Record<string, PhotoDescription>;
}

const MODELS = [
  { id: "google/gemma-4-31B-it", name: "Gemma 4 31B" },
  { id: "mistralai/Mistral-Small-4-119B-2603", name: "Mistral Small 4" },
];

interface Props {
  photo: ContactPhotoData;
  contactId: string;
  apiUrl: string;
  apiKey: string;
  onChange: (photo: ContactPhotoData) => void;
  onConflict?: () => Promise<void>;
}

export default function ContactPhotoDescriptions({ photo, contactId, apiUrl, apiKey, onChange, onConflict }: Props) {
  const [draft, setDraft] = React.useState(photo.user_description ?? "");
  const [saving, setSaving] = React.useState(false);
  const [running, setRunning] = React.useState<Record<string, boolean>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saved, setSaved] = React.useState(false);
  const currentPhoto = React.useRef(photo);
  currentPhoto.current = photo;
  const mounted = React.useRef(true);
  React.useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const base = photo.id ? `${apiUrl}/contact_photos/${photo.id}` : `${apiUrl}/contacts/${contactId}/photo`;
  const headers = { "x-api-key": apiKey };
  const errorText = (error: any) => error.response?.data?.message ?? "Nie udało się wykonać operacji. Spróbuj ponownie.";
  const busy = Object.values(running).some(Boolean);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    setErrors((old) => ({ ...old, user: "" }));
    try {
      const response = await axios.patch(`${base}/description`, {
        storage_key: photo.storage_key,
        user_description: draft,
        user_description_revision: photo.user_description_revision,
      }, { headers });
      if (!mounted.current) return;
      const updated = {
        ...currentPhoto.current,
        user_description: response.data.photo.user_description,
        user_description_revision: response.data.photo.user_description_revision,
      };
      currentPhoto.current = updated;
      onChange(updated);
      setDraft(updated.user_description ?? "");
      setSaved(true);
    } catch (error: any) {
      if (error.response?.status === 409 && onConflict) {
        try { await onConflict(); } catch { /* Keep the draft and the original conflict visible. */ }
      }
      if (mounted.current) setErrors((old) => ({ ...old, user: errorText(error) }));
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  const generate = async (model: string) => {
    setRunning((old) => ({ ...old, [model]: true }));
    setErrors((old) => ({ ...old, [model]: "" }));
    try {
      const response = await axios.post(`${base}/describe`, {
        storage_key: photo.storage_key, model,
      }, { headers });
      if (!mounted.current) return;
      // Each request owns only one model result, never the user's draft or
      // the concurrently generated result from the other model.
      const updated = {
        ...currentPhoto.current,
        ai_descriptions: {
          ...currentPhoto.current.ai_descriptions,
          [model]: response.data.photo.ai_descriptions[model],
        },
      };
      currentPhoto.current = updated;
      onChange(updated);
    } catch (error: any) {
      if (error.response?.status === 409 && onConflict) {
        try { await onConflict(); } catch { /* Keep the draft and the original conflict visible. */ }
      }
      if (mounted.current) setErrors((old) => ({ ...old, [model]: errorText(error) }));
    } finally {
      if (mounted.current) setRunning((old) => ({ ...old, [model]: false }));
    }
  };

  return <section aria-label="Opisy zdjęcia" style={{ marginBottom: 20 }}>
    <label htmlFor="photo-user-description"><strong>Twój opis zdjęcia</strong></label>
    <p style={{ margin: "6px 0" }}>Zapisz to, co wiesz: kto jest na zdjęciu, jakie są relacje i czy dzieci są bliźniętami. Generowanie AI nie zmienia tego opisu.</p>
    <p>Opis jest wspólny dla wszystkich kontaktów przypisanych do tego zdjęcia.</p>
    <textarea id="photo-user-description" value={draft} maxLength={12000} rows={4}
      disabled={saving}
      onChange={(event) => { setDraft(event.target.value); setSaved(false); }}
      style={{ width: "100%", boxSizing: "border-box" }} />
    <button type="button" className="button" disabled={saving || draft === (photo.user_description ?? "")}
      onClick={save}>{saving ? "Zapisywanie…" : "Zapisz swój opis"}</button>
    {saved && <span role="status" style={{ marginLeft: 8 }}>Zapisano opis.</span>}
    {errors.user && <p role="alert">{errors.user}</p>}

    <h3>Opisy AI — porównanie</h3>
    <p>Zdjęcie zostanie wysłane do CloudFerro Sherlock. Każdy model opisuje widoczną zawartość niezależnie; Twój opis nie jest wysyłany. Zgodność opisów nie potwierdza pokrewieństwa.</p>
    <p>Generowanie obsługuje JPEG i PNG do 5 MB.</p>
    <button type="button" className="button" disabled={busy}
      onClick={() => { void Promise.allSettled(MODELS.map((model) => generate(model.id))); }}>
      {busy ? "Generowanie opisów…" : "Wygeneruj i porównaj dwa opisy"}
    </button>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: 12, marginTop: 12 }}>
      {MODELS.map((model) => {
        const result = photo.ai_descriptions[model.id];
        return <article key={model.id} aria-label={`Opis ${model.name}`} style={{ border: "1px solid #d5dde8", borderRadius: 8, padding: 12 }}>
          <h4 style={{ marginTop: 0 }}>{model.name}</h4>
          <p style={{ whiteSpace: "pre-wrap" }}>{result?.text ?? "Brak opisu tego modelu."}</p>
          {result && <p style={{ fontSize: "0.85em", color: "#667085" }}>
            {new Date(result.generated_at).toLocaleString("pl-PL")}
            {result.prompt_tokens != null && result.completion_tokens != null && ` · Tokeny: ${result.prompt_tokens} wejścia / ${result.completion_tokens} wyjścia`}
            {result.latency_ms != null && ` · ${(result.latency_ms / 1000).toFixed(1)} s`}
          </p>}
          <button type="button" className="button" disabled={busy} onClick={() => { void generate(model.id); }}>
            {running[model.id] ? "Generowanie…" : result ? `Ponów opis — ${model.name}` : `Wygeneruj opis — ${model.name}`}
          </button>
          {errors[model.id] && <p role="alert">{errors[model.id]}</p>}
        </article>;
      })}
    </div>
  </section>;
}
