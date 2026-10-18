import React from "react";
import axios from "axios";

export type AddableEntityType = "persName" | "orgName" | "placeName" | "eventName";

const CHOICES: { type: AddableEntityType; label: string }[] = [
  { type: "persName", label: "👤 Osoba" },
  { type: "orgName", label: "🏢 Organizacja" },
  { type: "placeName", label: "📍 Miejsce" },
  { type: "eventName", label: "📅 Wydarzenie" },
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
  onClose: () => void;
  onAdded: (message: string) => void;
}

// Context menu over a selected fragment of the document text: turns it into a person, organization
// or place (POST /document/:id/entities/add_mention). The name field is the canonical form; typing an
// existing entity's name adds the fragment to it as a new surface form ("kaliningradzkiej enklawy"
// -> "Obwód Kaliningradzki").
const SelectionEntityMenu = ({ x, y, text, apiUrl, docId, headers, onClose, onAdded }: Props) => {
  const [name, setName] = React.useState(text);
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
      <label style={{ display: "block", marginBottom: 8 }}>
        Nazwa encji
        <input type="text" value={name} aria-label="Nazwa encji" maxLength={200} autoFocus
          onChange={(event) => setName(event.target.value)} style={{ width: "100%", boxSizing: "border-box" }} />
      </label>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {CHOICES.map((choice) => (
          <button key={choice.type} type="button" role="menuitem" disabled={busy || !name.trim()}
            onClick={() => void add(choice.type)}>{choice.label}</button>
        ))}
        <button type="button" onClick={onClose}>Anuluj</button>
      </div>
      {error && <p role="alert" style={{ color: "#a33", margin: "6px 0 0" }}>{error}</p>}
    </div>
  );
};

export default SelectionEntityMenu;
