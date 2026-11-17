import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { changesInChapter, regionLabel, type RegionDictionaryInfo } from "../../utils/regionDictionary";

// "Słownik regionu „Jemen” — w tym rozdziale zastosowano (N):" — the twin of the channel-glossary note on /ner/:id.
// The channel glossary repairs a COPY of the text for NER; the region dictionary rewrites the stored transcript
// (stored rules, POST /transcript_corrections/apply), so what it changed is read from the audit rows. Remaining
// changes are applied from here in two steps: a preview (dry run), then an explicit save.

type Props = {
  documentId: string;
  position: number;
  info: RegionDictionaryInfo | null;
  apiUrl: string;
  apiKey: string;
  // Called after the text was rewritten, so the page can reload its chapters and the audit rows.
  onChanged: () => void;
};

type Preview = { before: string; after: string } | null;

const errorText = (failure: unknown, fallback: string) => {
  const response = (failure as { response?: { data?: { message?: string } } }).response;
  return response?.data?.message ?? fallback;
};

const ChapterRegionDictionary = ({ documentId, position, info, apiUrl, apiKey, onChanged }: Props) => {
  const [preview, setPreview] = React.useState<Preview>(null);
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const [refreshEntities, setRefreshEntities] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState("");

  if (!info) return null;
  const lines = changesInChapter(info, position);
  if (info.dictionaries.length === 0 && info.applications.length === 0) return null;

  const headers = { "x-api-key": apiKey, "Content-Type": "application/json" };

  const openPreview = async () => {
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/transcript_corrections/apply`,
        { document_id: Number(documentId), dry_run: true }, { headers });
      const snippet = response.data?.fields?.text?.snippet as { before: string; after: string } | null | undefined;
      setPreview(snippet ?? null);
      setPreviewOpen(true);
    } catch (failure) {
      setError(errorText(failure, "Nie udało się przygotować podglądu poprawek."));
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true); setError(""); setMessage("");
    try {
      await axios.post(`${apiUrl}/transcript_corrections/apply`,
        { document_id: Number(documentId), dry_run: false }, { headers });
      if (refreshEntities) {
        await axios.post(`${apiUrl}/website_entities`, new URLSearchParams({ id: documentId }),
          { headers: { "x-api-key": apiKey }, timeout: 150000 });
      }
      setPreviewOpen(false);
      setMessage(refreshEntities
        ? "Poprawki zapisane w tekście, encje odświeżone."
        : "Poprawki zapisane w tekście. Odśwież encje („Wykryj osoby i miejsca”), żeby je uwzględnić.");
      onChanged();
    } catch (failure) {
      setError(errorText(failure, "Nie udało się zapisać poprawek (zapis wymaga klucza user lub service)."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div role="note" aria-label="Słownik regionu" style={{ marginTop: 6 }}>
      <strong>
        Słownik regionu „{regionLabel(info)}” — w tym rozdziale zastosowano{lines.length > 0 ? ` (${lines.length})` : ""}:
      </strong>
      <div style={{ marginTop: 6, paddingLeft: 8, borderLeft: "3px solid #bbf7d0" }}>
        {lines.length === 0
          ? <small style={{ color: "#64748b" }}>Słownik regionu nie zmieniał tego rozdziału.</small>
          : <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
              {lines.map((line) => (
                <li key={`${line.original}→${line.replacement}`} style={{ marginBottom: 4 }}>
                  {line.original} → <strong>{line.replacement}</strong> ×{line.occurrences}
                </li>
              ))}
            </ul>}
        {info.dictionaries.length > 0 && (
          <details style={{ marginTop: 2, fontSize: "0.9em" }}>
            <summary>Słowniki regionów dokumentu ({info.dictionaries.length})</summary>
            {info.dictionaries.map((dictionary) => `${dictionary.country_name ?? dictionary.country_slug}: ${dictionary.rules} reguł`).join("; ")}
          </details>
        )}
        {info.pending_changes > 0 && (
          <div style={{ marginTop: 6 }}>
            <small>Słownik ma jeszcze <strong>{info.pending_changes}</strong> zmian do zastosowania w tekście dokumentu.</small>{" "}
            {!previewOpen && (
              <button type="button" disabled={busy} onClick={openPreview}>Zastosuj słownik regionu…</button>
            )}
          </div>
        )}
        {previewOpen && (
          <div role="group" aria-label="Podgląd poprawek słownika regionu" style={{ marginTop: 6, padding: 8, background: "#f8fafc", border: "1px solid #cbd5e1", borderRadius: 6 }}>
            <small>Podgląd (nic jeszcze nie zapisano). Zmiana dotyczy całego dokumentu, nie tylko tego rozdziału; pierwsza zmiana:</small>
            {preview
              ? <pre style={{ whiteSpace: "pre-wrap", margin: "4px 0" }}>{`przed: …${preview.before}…\npo:    …${preview.after}…`}</pre>
              : <p style={{ margin: "4px 0" }}>Brak zmian do zapisania.</p>}
            <label style={{ display: "block", marginBottom: 6 }}>
              <input type="checkbox" checked={refreshEntities} onChange={(event) => setRefreshEntities(event.target.checked)} />
              {" "}Odśwież encje po zapisie (może potrwać do 2 minut)
            </label>
            <button type="button" disabled={busy || !preview} onClick={save}>Zapisz zmiany w tekście</button>{" "}
            <button type="button" disabled={busy} onClick={() => setPreviewOpen(false)}>Anuluj</button>
            <div><small style={{ color: "#64748b" }}>Chunki i embeddingi nie są przebudowywane.</small></div>
          </div>
        )}
        {busy && <small role="status" style={{ color: "#64748b" }}>Pracuję…</small>}
        {message && <div role="status" style={{ color: "#15803d" }}>{message}</div>}
        {error && <div role="alert" style={{ color: "#b91c1c" }}>{error}</div>}
        <small>
          Reguły regionu poprawiają zapisany tekst (inaczej niż słownik kanału).{" "}
          <Link to="/dictionaries?tab=region">Słowniki →</Link>
        </small>
      </div>
    </div>
  );
};

export default ChapterRegionDictionary;
