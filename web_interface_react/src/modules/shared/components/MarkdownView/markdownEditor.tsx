import React from "react";
import MarkdownView from "./markdownView";
import { cleanObsidianNote } from "./obsidianNote";

type Props = {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  label: string;
  /** Tool name: a leading heading with the same text is dropped when cleaning a pasted Obsidian note. */
  toolName?: string;
};

// Markdown source on the left, live preview on the right (stacked on a narrow screen).
export default function MarkdownEditor({ value, onChange, disabled, label, toolName }: Props) {
  const cleaned = React.useMemo(() => cleanObsidianNote(value, toolName), [value, toolName]);
  const canClean = cleaned.removed.length > 0;
  const [lastCleaned, setLastCleaned] = React.useState<{ before: string; removed: string[] } | null>(null);

  const clean = () => {
    setLastCleaned({ before: value, removed: cleaned.removed });
    onChange(cleaned.markdown);
  };
  const undo = () => {
    if (!lastCleaned) return;
    onChange(lastCleaned.before);
    setLastCleaned(null);
  };

  return <div>
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
      <button type="button" disabled={disabled || !canClean} onClick={clean}
        title={"Usuwa z wklejonej notatki to, co jest już osobnymi polami narzędzia albo śmieciem z szablonu: " +
          "front matter z tagami, linie Licence / Type of application / Pricing type / homepage / pricing page, " +
          "nagłówek z nazwą narzędzia, sekcję Metadata i znaczniki Templatera."}>
        Oczyść notatkę z Obsidiana
      </button>
      {lastCleaned && <span role="status" style={{ color: "#166534", fontSize: ".85rem" }}>
        Usunięto: {lastCleaned.removed.join(", ")}. <button type="button" onClick={undo}>Cofnij</button>
      </span>}
      {!lastCleaned && <span style={{ color: "#64748b", fontSize: ".85rem" }}>
        Wklej tu notatkę z Obsidiana (Markdown) — podgląd po prawej pokazuje, jak będzie wyglądać.
      </span>}
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12 }}>
      <textarea aria-label={label} value={value} onChange={event => onChange(event.target.value)} rows={18} disabled={disabled}
        spellCheck={false}
        style={{ width: "100%", boxSizing: "border-box", fontFamily: "monospace", fontSize: ".85rem", lineHeight: 1.5, minHeight: 260 }} />
      <div aria-label="Podgląd notatki" style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "4px 14px 10px", overflow: "auto", maxHeight: 520, background: "#fff" }}>
        {value.trim() ? <MarkdownView text={value} /> : <p style={{ color: "#94a3b8" }}>Podgląd pojawi się tutaj.</p>}
      </div>
    </div>
  </div>;
}
