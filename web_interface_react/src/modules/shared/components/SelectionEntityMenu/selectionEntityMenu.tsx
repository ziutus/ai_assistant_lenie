import React from "react";
import axios from "axios";
import { copyText } from "../../utils/copyText";

export type AddableEntityType = "persName" | "orgName" | "placeName" | "eventName" | "productName" | "conceptName";

const CHOICES: { type: AddableEntityType; label: string }[] = [
  { type: "persName", label: "👤 Osoba" },
  { type: "orgName", label: "🏢 Organizacja" },
  { type: "placeName", label: "📍 Miejsce" },
  { type: "eventName", label: "📅 Wydarzenie" },
  { type: "productName", label: "🛰️ Produkt / system" },
  { type: "conceptName", label: "💡 Pojęcie / ideologia" },
];

// The text a reviewer selected, normalized like the backend does (one line, single spaces) and
// capped at the backend limit; "" means there is nothing worth a menu.
export function selectedFragment(selection: Selection | null): string {
  const text = selection?.toString().replace(/\s+/g, " ").trim() ?? "";
  return text.length > 200 ? "" : text;
}

interface Props {
  x: number;
  y: number;
  text: string;
  apiUrl: string;
  docId: string;
  headers: Record<string, string>;
  // The document's channel (byline); enables the channel-only scope of a transcript fix.
  byline?: string;
  onClose: () => void;
  onAdded: (message: string) => void;
}

// Context menu over a selected fragment of the document text: turns it into a person, organization
// or place (POST /document/:id/entities/add_mention). The name field is the canonical form; typing an
// existing entity's name adds the fragment to it as a new surface form ("kaliningradzkiej enklawy"
// -> "Obwód Kaliningradzki").
const SelectionEntityMenu = ({ x, y, text, apiUrl, docId, headers, byline, onClose, onAdded }: Props) => {
  const [name, setName] = React.useState(text);
  const [fixing, setFixing] = React.useState(false);
  // "Do słownika kanału": the selected spelling becomes an alias of a name in the channel glossary.
  const [glossaryMode, setGlossaryMode] = React.useState(false);
  const [glossaryName, setGlossaryName] = React.useState("");
  const [replacement, setReplacement] = React.useState(text);
  const [channelOnly, setChannelOnly] = React.useState(false);
  // Replace in this document only: no stored rule, so even a single word is allowed.
  const [documentOnly, setDocumentOnly] = React.useState(false);
  const channel = byline?.trim() ?? "";
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [onClose]);

  const copy = async () => {
    if (await copyText(text)) onClose();
    else setError("Nie udało się skopiować — zaznacz tekst i użyj Ctrl+C.");
  };

  // Opens a Google search for the selected fragment (not the entity-name field, which may be edited
  // into a canonical form) in a new tab.
  const searchGoogle = () => {
    window.open(`https://www.google.com/search?q=${encodeURIComponent(text)}`, "_blank", "noopener,noreferrer");
    onClose();
  };

  // "Popraw błąd w transkrypcji": stores a literal phrase rule (POST /transcript_corrections, applied to
  // every future transcript) and rewrites this document's text now (POST /transcript_corrections/apply).
  // Entities are not rebuilt by the backend, so the page refreshes the panel and the reviewer re-runs NER.
  const fixTranscript = async () => {
    if (busy) return;
    const fixed = replacement.trim();
    if (!fixed || fixed === text) {
      setError("Wpisz poprawną wersję zaznaczonej frazy.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (!documentOnly) {
        try {
          await axios.post(`${apiUrl}/transcript_corrections`, {
            pattern: text, replacement: fixed,
            ...(channelOnly && channel ? { scope: "author", author: channel } : { scope: "global" }),
          }, { headers });
        } catch (failure) {
          // 409: the same rule already exists — still rewrite this document.
          if (!(axios.isAxiosError(failure) && failure.response?.status === 409)) throw failure;
        }
      }
      // With a pattern the backend replaces it in this document only, never storing a rule.
      const applied = await axios.post(`${apiUrl}/transcript_corrections/apply`,
        { document_id: Number(docId), dry_run: false, ...(documentOnly ? { pattern: text, replacement: fixed } : {}) },
        { headers });
      const changed = Object.values(applied.data.fields ?? {}).some((field) => (field as { changed?: boolean }).changed);
      onAdded(changed
        ? `Poprawiono „${text}” → „${fixed}” w transkrypcji. Uruchom ponownie wykrywanie encji, aby odświeżyć chipy.`
        : `${documentOnly ? "Nie zapisano reguły" : "Zapisano regułę"} „${text}” → „${fixed}”, ale w tym dokumencie nic się nie zmieniło.`);
    } catch (failure) {
      const data = axios.isAxiosError(failure) ? failure.response?.data : undefined;
      if (axios.isAxiosError(failure) && failure.response?.status === 403) {
        setError("Ten klucz API nie może zapisywać poprawek transkrypcji.");
      } else {
        setError(data?.message ?? "Nie udało się poprawić transkrypcji.");
      }
      setBusy(false);
    }
  };

  // Stores the selected spelling as an alias of `glossaryName` in the channel glossary (ner_channel_glossary):
  // applied to a copy of the text before NER, so a word the author uses in a special sense (YouTube
  // algorithm workarounds: "Rzymianie" for Jews) reads as the intended name. A second spelling of the
  // same name is appended to the existing entry. Takes effect on the next entity refresh.
  const addToGlossary = async () => {
    if (busy) return;
    const canonical = glossaryName.trim();
    if (!canonical) {
      setError("Wpisz nazwę, którą ma oznaczać zaznaczona fraza.");
      return;
    }
    if (text.length < 3) {
      setError("Fraza w słowniku musi mieć co najmniej 3 znaki.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      try {
        await axios.post(`${apiUrl}/ner_channel_glossary`,
          { author: channel, canonical_name: canonical, aliases: [text], fuzzy: false }, { headers });
      } catch (failure) {
        if (!(axios.isAxiosError(failure) && failure.response?.status === 409)) throw failure;
        // The channel already has this name: add the spelling to that entry.
        const listed = await axios.get(`${apiUrl}/ner_channel_glossary`, { headers, params: { author: channel } });
        const existing = (listed.data.entries ?? []).find(
          (entry: { canonical_name: string }) => entry.canonical_name.toLowerCase() === canonical.toLowerCase());
        if (!existing) throw failure;
        const aliases: string[] = existing.aliases ?? [];
        if (!aliases.includes(text)) {
          await axios.patch(`${apiUrl}/ner_channel_glossary/${existing.id}`, { aliases: [...aliases, text] }, { headers });
        }
      }
      onAdded(`Dodano do słownika kanału „${channel}”: „${text}” → „${canonical}”. Odśwież encje dokumentu (ponowne wykrywanie), aby zadziałało.`);
    } catch (failure) {
      const data = axios.isAxiosError(failure) ? failure.response?.data : undefined;
      if (axios.isAxiosError(failure) && failure.response?.status === 403) {
        setError("Ten klucz API nie może zapisywać słownika kanału.");
      } else {
        setError(data?.message ?? "Nie udało się dodać do słownika kanału.");
      }
      setBusy(false);
    }
  };

  const add = async (entityType: AddableEntityType) => {
    if (busy) return;
    setBusy(true);
    setError("");
    const trimmed = name.trim();
    try {
      const response = await axios.post(`${apiUrl}/document/${docId}/entities/add_mention`, {
        text, entity_type: entityType, ...(trimmed && trimmed !== text ? { name: trimmed } : {}),
      }, { headers });
      onAdded(`Dodano „${response.data.entity_text}” (${response.data.mention_count}×).`);
    } catch (failure) {
      const data = axios.isAxiosError(failure) ? failure.response?.data : undefined;
      if (data?.code === "entity_exists") {
        setError(`To już encja „${data.entity?.entity_text}” — zmień jej typ z menu jej chipa.`);
      } else {
        setError(data?.message ?? "Nie udało się dodać encji.");
      }
      setBusy(false);
    }
  };

  const left = Math.max(8, Math.min(x, window.innerWidth - 300));
  const top = Math.max(8, Math.min(y, window.innerHeight - 220));
  return (
    <div ref={ref} role="menu" aria-label="Dodaj encję z zaznaczenia"
      style={{
        position: "fixed", left, top, zIndex: 1000, width: 280, padding: 10, background: "#fff",
        border: "1px solid #94a3b8", borderRadius: 8, boxShadow: "0 4px 16px rgba(0,0,0,0.25)", fontSize: "0.9em",
      }}>
      <div style={{ marginBottom: 6 }}>Zaznaczono: <strong>„{text}”</strong></div>
      {glossaryMode ? (
        <>
          <label style={{ display: "block", marginBottom: 8 }}>
            Oznacza (nazwa w słowniku)
            <input type="text" value={glossaryName} aria-label="Nazwa w słowniku" maxLength={200} autoFocus
              placeholder="np. Żydzi" onChange={(event) => setGlossaryName(event.target.value)}
              style={{ width: "100%", boxSizing: "border-box" }} />
          </label>
          <p style={{ margin: "0 0 8px", color: "#475569" }}>
            W słowniku kanału „{channel}” fraza „{text}” będzie czytana jako ta nazwa przy wykrywaniu encji
            (tekst transkrypcji się nie zmienia). Dodaj osobno każdą odmianę (np. „Rzymian”, „Rzymianie”).
          </p>
          <div style={{ display: "flex", gap: 6 }}>
            <button type="button" disabled={busy} onClick={() => void addToGlossary()}>📖 Dodaj do słownika</button>
            <button type="button" disabled={busy} onClick={() => setGlossaryMode(false)}>Wstecz</button>
          </div>
        </>
      ) : fixing ? (
        <>
          <label style={{ display: "block", marginBottom: 8 }}>
            Poprawna wersja
            <input type="text" value={replacement} aria-label="Poprawna wersja" maxLength={200} autoFocus
              onChange={(event) => setReplacement(event.target.value)} style={{ width: "100%", boxSizing: "border-box" }} />
          </label>
          <label style={{ display: "block", marginBottom: 8 }}>
            <input type="checkbox" checked={documentOnly} onChange={(event) => setDocumentOnly(event.target.checked)} />
            {" "}Tylko ten dokument (bez zapisywania reguły)
          </label>
          {channel && !documentOnly && (
            <label style={{ display: "block", marginBottom: 8 }}>
              <input type="checkbox" checked={channelOnly} onChange={(event) => setChannelOnly(event.target.checked)} />
              {" "}Tylko dla kanału „{channel}”
            </label>
          )}
          <p style={{ margin: "0 0 8px", color: "#475569" }}>
            {documentOnly
              ? "Zmiana dotyczy tylko tego dokumentu (też pojedyncze słowo); żadna reguła nie zostanie zapisana."
              : "Reguła obejmie też przyszłe transkrypcje (fraza, nie pojedyncze słowo); ten dokument zostanie poprawiony od razu."}
          </p>
          <div style={{ display: "flex", gap: 6 }}>
            <button type="button" disabled={busy} onClick={() => void fixTranscript()}>✏️ Popraw w transkrypcji</button>
            <button type="button" disabled={busy} onClick={() => setFixing(false)}>Wstecz</button>
          </div>
        </>
      ) : (
        <>
          <label style={{ display: "block", marginBottom: 8 }}>
            Nazwa encji
            <input type="text" value={name} aria-label="Nazwa encji" maxLength={200} autoFocus
              onChange={(event) => setName(event.target.value)} style={{ width: "100%", boxSizing: "border-box" }} />
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            <button type="button" role="menuitem" onClick={() => void copy()}>📋 Kopiuj</button>
            {CHOICES.map((choice) => (
              <button key={choice.type} type="button" role="menuitem" disabled={busy || !name.trim()}
                onClick={() => void add(choice.type)}>{choice.label}</button>
            ))}
            <button type="button" role="menuitem" onClick={() => { setError(""); setFixing(true); }}>
              ✏️ Popraw błąd w transkrypcji
            </button>
            {channel && (
              <button type="button" role="menuitem" onClick={() => { setError(""); setGlossaryMode(true); }}>
                📖 Do słownika kanału
              </button>
            )}
            <button type="button" role="menuitem" onClick={searchGoogle}>🔍 Szukaj w Google</button>
            <button type="button" onClick={onClose}>Anuluj</button>
          </div>
        </>
      )}
      {error && <p role="alert" style={{ color: "#a33", margin: "6px 0 0" }}>{error}</p>}
    </div>
  );
};

export default SelectionEntityMenu;
