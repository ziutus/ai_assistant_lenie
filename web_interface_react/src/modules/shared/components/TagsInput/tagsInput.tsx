import React from "react";

// Chip editor over a CSV string (web_documents.tags stays a comma-separated
// column — no DB migration). Enter/comma adds a tag, × removes one;
// suggestions come from GET /tags via a <datalist>.

const chipStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  padding: "2px 8px",
  margin: "2px 4px 2px 0",
  borderRadius: "10px",
  background: "#eef2f7",
  border: "1px solid #c3cfdd",
  fontSize: "0.85em",
};

interface TagsInputProps {
  value: string; // CSV
  onChange: (csv: string) => void;
  suggestions?: string[];
  disabled?: boolean;
  label?: string;
}

const TagsInput = ({ value, onChange, suggestions, disabled, label }: TagsInputProps) => {
  const [draft, setDraft] = React.useState("");
  const tags = (value || "").split(",").map((t) => t.trim()).filter(Boolean);

  const addDraft = () => {
    const tag = draft.trim().replace(/,+$/, "");
    if (!tag) {
      return;
    }
    if (!tags.includes(tag)) {
      onChange([...tags, tag].join(","));
    }
    setDraft("");
  };

  const remove = (tag: string) => {
    onChange(tags.filter((t) => t !== tag).join(","));
  };

  return (
    <div style={{ margin: "6px 0" }}>
      {label && <label style={{ display: "block" }}>{label}</label>}
      <div>
        {tags.map((tag) => (
          <span key={tag} style={chipStyle}>
            {tag}
            {!disabled && (
              <button
                type="button"
                onClick={() => remove(tag)}
                style={{ border: "none", background: "transparent", cursor: "pointer", padding: 0, color: "#a33" }}
                title="Usuń tag"
              >
                ×
              </button>
            )}
          </span>
        ))}
        <input
          value={draft}
          disabled={disabled}
          list="tags-suggestions"
          placeholder="dodaj tag…"
          onChange={(e) => {
            // a trailing comma commits the tag immediately (also covers fast typing)
            if (e.target.value.endsWith(",")) {
              const tag = e.target.value.slice(0, -1).trim();
              if (tag && !tags.includes(tag)) {
                onChange([...tags, tag].join(","));
              }
              setDraft("");
              return;
            }
            setDraft(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addDraft();
            }
          }}
          onBlur={addDraft}
          style={{ padding: "3px 8px", minWidth: 160, margin: "2px 0" }}
        />
        {suggestions && suggestions.length > 0 && (
          <datalist id="tags-suggestions">
            {suggestions.filter((s) => !tags.includes(s)).map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        )}
      </div>
    </div>
  );
};

export default TagsInput;
