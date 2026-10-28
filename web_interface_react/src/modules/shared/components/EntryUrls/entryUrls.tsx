import React from "react";
import { Link } from "react-router-dom";

type EntryUrl = {
  url: string; host: string; origin: string;
  document: { id: number; title: string | null; document_type: string } | null;
};

type Props = { recommendationId: number; apiUrl: string; headers: Record<string, string>; onImported?: () => void };

const originLabels: Record<string, string> = {
  description: "opis", source_context: "kontekst", homepage_url: "strona", source_url: "źródło", links: "linki",
};

// Links written inside a radar entry. The detector sometimes records an article as a "tool"; this lets the reader
// send the linked page straight to the knowledge base instead of copying the address by hand.
export default function EntryUrls({ recommendationId, apiUrl, headers, onImported }: Props) {
  const [urls, setUrls] = React.useState<EntryUrl[] | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState("");

  const load = React.useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/${recommendationId}/urls`, { headers });
      if (!response.ok) throw new Error("Nie udało się wyszukać linków");
      setUrls((await response.json()).urls as EntryUrl[]);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się wyszukać linków"); }
  }, [apiUrl, headers, recommendationId]);

  const add = async (url: string) => {
    setBusy(url); setError("");
    try {
      const response = await fetch(`${apiUrl}/tool_recommendations/${recommendationId}/import_url`, {
        method: "POST", headers, body: JSON.stringify({ url }),
      });
      if (!response.ok) throw new Error("Nie udało się dodać linku do bazy wiedzy");
      const result = await response.json() as { promotion_failed?: string };
      if (result.promotion_failed) setError(`Dodano jako link, ale treści nie udało się pobrać (${result.promotion_failed}). Otwórz go i użyj „Zaimportuj jako webpage" z przeglądarki.`);
      else await load();
      onImported?.();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się dodać linku"); }
    finally { setBusy(null); }
  };

  React.useEffect(() => { void load(); }, [load]);

  if (urls === null || (urls.length === 0 && !error)) return null;
  return <div style={{ margin: "8px 0", fontSize: ".85rem" }}>
    <strong>Linki w treści</strong>
    <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
      {urls.map(entry => <li key={entry.url} style={{ marginBottom: 4 }}>
        <a href={entry.url} target="_blank" rel="noreferrer">{entry.url}</a>
        <span style={{ color: "#64748b" }}> · {originLabels[entry.origin] ?? entry.origin}</span>{" "}
        {entry.document
          ? <Link to={`/${entry.document.document_type === "link" ? "link" : "webpage"}/${entry.document.id}`}>✓ w bazie wiedzy (#{entry.document.id})</Link>
          : <button type="button" disabled={busy === entry.url} onClick={() => void add(entry.url)}
            title="Dodaje ten adres do biblioteki jako dokument typu link; treść pobierzesz później z jego strony.">
            {busy === entry.url ? "Dodaję…" : "＋ Dodaj do bazy wiedzy"}</button>}
      </li>)}
    </ul>
    {error && <span role="alert" style={{ color: "#b91c1c" }}>{error}</span>}
  </div>;
}
