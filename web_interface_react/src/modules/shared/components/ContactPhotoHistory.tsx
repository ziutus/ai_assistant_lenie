import React from "react";
import axios from "axios";
import { type ContactPhotoData } from "./ContactPhotoDescriptions";

interface HistoryItem extends ContactPhotoData {
  created_at: string;
  is_current: boolean;
  photo_url: string | null;
  thumbnail_url: string | null;
}

interface Props {
  contactId: string;
  apiUrl: string;
  apiKey: string;
  onRestored: (photoUrl: string, photo: ContactPhotoData) => void;
}

export default function ContactPhotoHistory({ contactId, apiUrl, apiKey, onRestored }: Props) {
  const [history, setHistory] = React.useState<HistoryItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const [restoring, setRestoring] = React.useState<string | null>(null);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const mounted = React.useRef(true);
  React.useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  const headers = { "x-api-key": apiKey };
  const errorText = (error: any) => error.response?.data?.message ?? "Nie udało się wykonać operacji. Spróbuj ponownie.";

  const loadHistory = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await axios.get(`${apiUrl}/contacts/${contactId}/photo/history`, { headers });
      if (!mounted.current) return;
      setHistory(response.data.history);
      setLoaded(true);
    } catch (error) {
      if (mounted.current) setError(errorText(error));
    } finally {
      if (mounted.current) setLoading(false);
    }
  };

  const restore = async (storageKey: string) => {
    setRestoring(storageKey);
    setErrors((old) => ({ ...old, [storageKey]: "" }));
    try {
      const response = await axios.post(`${apiUrl}/contacts/${contactId}/photo/restore`, {
        storage_key: storageKey,
      }, { headers });
      if (!mounted.current) return;
      onRestored(response.data.photo_url, response.data.photo);
      await loadHistory();
    } catch (error) {
      if (mounted.current) setErrors((old) => ({ ...old, [storageKey]: errorText(error) }));
    } finally {
      if (mounted.current) setRestoring(null);
    }
  };

  return <details style={{ marginBottom: 20 }} onToggle={(event) => {
    if (event.currentTarget.open && !loaded && !loading) void loadHistory();
  }}>
    <summary>Historia zdjęć</summary>
    {loading && <p role="status">Ładowanie historii zdjęć…</p>}
    {error && <p role="alert">{error} <button type="button" disabled={loading}
      onClick={() => { void loadHistory(); }}>Spróbuj ponownie</button></p>}
    {loaded && !loading && history.length === 0 && <p>Brak zdjęć w historii.</p>}
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: 12, marginTop: 12 }}>
      {history.map((item) => {
        const imageUrl = item.thumbnail_url || item.photo_url;
        return <article key={item.storage_key} style={{ border: "1px solid #d5dde8", borderRadius: 8, padding: 12 }}>
          {imageUrl ? <img src={imageUrl} alt="Zdjęcie z historii kontaktu"
            style={{ width: "100%", height: 200, objectFit: "contain" }} /> : <p>Brak zdjęcia</p>}
          <p>{new Date(item.created_at).toLocaleString("pl-PL")}</p>
          <button type="button" className="button" disabled={item.is_current || restoring !== null || loading}
            onClick={() => { void restore(item.storage_key); }}>
            {item.is_current ? "Aktualne zdjęcie" : restoring === item.storage_key ? "Przywracanie…" : "Przywróć to zdjęcie"}
          </button>
          {errors[item.storage_key] && <p role="alert">{errors[item.storage_key]}</p>}
        </article>;
      })}
    </div>
  </details>;
}
