import React from "react";

export type LinkedDocument = {
  id: number; relation_type: string; context: string | null;
  recommender_document: { id: number; title: string | null; url: string | null; discovery_source: string | null } | null;
};

type Props = {
  recommendationId: number; apiUrl: string; headers: Record<string, string>;
  evidences: LinkedDocument[]; disabled?: boolean; onChanged: () => void | Promise<void>;
};

// Library documents (a video, an article) that talk about the tool. Stored as `mentioned_in` evidence of the
// radar entry, so they show up under "Dlaczego jest w radarze?" and feed relation detection.
export default function EntryDocuments({ recommendationId, apiUrl, headers, evidences, disabled, onChanged }: Props) {
  const [reference, setReference] = React.useState("");
  const [context, setContext] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [confirming, setConfirming] = React.useState<number | null>(null);

  const linked = evidences.filter(evidence => evidence.relation_type === "mentioned_in" && evidence.recommender_document);
  const base = `${apiUrl}/tool_recommendations/${recommendationId}/documents`;

  const attach = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!reference.trim()) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await fetch(base, {
        method: "POST", headers,
        body: JSON.stringify({ document: reference.trim(), ...(context.trim() ? { context: context.trim() } : {}) }),
      });
      const data = await response.json().catch(() => ({})) as { message?: string; created?: boolean };
      if (!response.ok) throw new Error(String(data.message || "Nie udało się powiązać dokumentu"));
      setMessage(data.created === false ? "Ten dokument był już powiązany z wpisem." : "Dokument powiązany z wpisem.");
      setReference(""); setContext("");
      await onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się powiązać dokumentu"); }
    finally { setBusy(false); }
  };

  const detach = async (documentId: number) => {
    if (confirming !== documentId) { setConfirming(documentId); return; }
    setBusy(true); setError(""); setMessage(""); setConfirming(null);
    try {
      const response = await fetch(`${base}/${documentId}`, { method: "DELETE", headers });
      const data = await response.json().catch(() => ({})) as { message?: string };
      if (!response.ok) throw new Error(String(data.message || "Nie udało się odpiąć dokumentu"));
      await onChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się odpiąć dokumentu"); }
    finally { setBusy(false); }
  };

  return <div style={{ margin: "8px 0", fontSize: ".85rem" }}>
    {linked.length > 0 && <div style={{ marginBottom: 6 }}>
      <strong>Powiązane dokumenty</strong>
      <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
        {linked.map(evidence => {
          const document = evidence.recommender_document!;
          return <li key={evidence.id} style={{ marginBottom: 4 }}>
            {document.title || document.url || `dokument #${document.id}`}
            <span style={{ color: "#64748b" }}> · #{document.id}{document.discovery_source ? ` · ${document.discovery_source}` : ""}</span>
            {document.url && <> · <a href={document.url} target="_blank" rel="noreferrer">otwórz</a></>}
            {evidence.context && <div style={{ color: "#64748b" }}>{evidence.context}</div>}
            {" "}<button type="button" disabled={disabled || busy} onClick={() => void detach(document.id)}
              onBlur={() => setConfirming(current => current === document.id ? null : current)}
              title="Usuwa tylko powiązanie z tym wpisem radaru; sam dokument zostaje w bibliotece.">
              {confirming === document.id ? "Na pewno odpiąć?" : "Odepnij"}</button>
          </li>;
        })}
      </ul>
    </div>}
    <details>
      <summary style={{ cursor: "pointer", color: "#475569" }}>📎 Powiąż z dokumentem</summary>
      <form onSubmit={event => void attach(event)} aria-label="Powiąż wpis radaru z dokumentem"
        style={{ display: "flex", gap: 8, alignItems: "end", flexWrap: "wrap", marginTop: 6 }}>
        <label style={{ flex: "2 1 240px" }}>Dokument (ID, ścieżka lub adres)
          <input value={reference} onChange={event => setReference(event.target.value)} style={{ width: "100%", display: "block", marginTop: 4 }}
            placeholder="np. 9332, /youtube/9332 albo https://www.youtube.com/watch?v=…" /></label>
        <label style={{ flex: "1 1 180px" }}>Uwaga (opcjonalnie)
          <input value={context} onChange={event => setContext(event.target.value)} style={{ width: "100%", display: "block", marginTop: 4 }}
            placeholder="np. film pokazuje działanie" /></label>
        <button type="submit" disabled={disabled || busy || !reference.trim()}>{busy ? "Łączę…" : "Powiąż"}</button>
      </form>
      <div style={{ color: "#64748b", marginTop: 4 }}>Dokument musi już być w bibliotece (film z adresu YouTube też).</div>
    </details>
    {message && <div role="status" style={{ color: "#166534" }}>{message}</div>}
    {error && <div role="alert" style={{ color: "#b91c1c" }}>{error}</div>}
  </div>;
}
