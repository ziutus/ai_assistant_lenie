import React from "react";

export type ProfileSuggestion = {
  status: "ok" | "error"; model: string; error_code?: string;
  description?: string; category?: string | null; category_is_new?: boolean; category_changed?: boolean;
  tags?: string[]; confidence?: "known" | "partial" | "unknown";
  tokens: number | null; cost: string | null; currency: string | null;
};

const sameText = (a: string, b: string) => a.trim().replace(/\s+/g, " ").toLowerCase() === b.trim().replace(/\s+/g, " ").toLowerCase();
const chip: React.CSSProperties = { background: "#dcfce7", color: "#166534", border: "1px dashed #16a34a", borderRadius: 999, padding: "2px 8px", fontSize: ".75rem", cursor: "pointer", marginRight: 4 };

const CONFIDENCE_TEXT: Record<string, { text: string; color: string }> = {
  known: { text: "model zna to narzędzie", color: "#166534" },
  partial: { text: "model zna je tylko częściowo — sprawdź opis", color: "#92400e" },
  unknown: { text: "model nie zna tego narzędzia — niczego nie wymyślał", color: "#991b1b" },
};

/**
 * ONE request to the chosen model returns a description, a category and tags for a radar entry (the context is
 * sent and paid for once). Each part is accepted separately; nothing is saved without a click.
 */
export default function ToolProfileSuggest({ description, category, tags, disabled, onSuggest, onUseDescription, onUseCategory, onAddTags }: {
  description: string | null; category: string | null; tags: string[]; disabled: boolean;
  onSuggest: () => Promise<ProfileSuggestion>;
  onUseDescription: (text: string) => void | Promise<void>;
  onUseCategory: (category: string) => void | Promise<void>;
  onAddTags: (tags: string[]) => void | Promise<void>;
}) {
  const [asking, setAsking] = React.useState(false);
  const [error, setError] = React.useState("");
  const [suggestion, setSuggestion] = React.useState<ProfileSuggestion | null>(null);
  const [descriptionDone, setDescriptionDone] = React.useState(false);
  const [categoryDone, setCategoryDone] = React.useState(false);
  const [acceptedTags, setAcceptedTags] = React.useState<string[]>([]);

  const ask = async () => {
    setAsking(true); setError(""); setSuggestion(null);
    setDescriptionDone(false); setCategoryDone(false); setAcceptedTags([]);
    try {
      const result = await onSuggest();
      if (result.status === "error") setError(`Model ${result.model} nie zwrócił użytecznej odpowiedzi (${result.error_code ?? "błąd"}). Spróbuj innego modelu.`);
      else setSuggestion(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Nie udało się pobrać podpowiedzi"); }
    finally { setAsking(false); }
  };

  const addTags = async (added: string[]) => {
    if (!added.length) return;
    setAcceptedTags(current => [...current, ...added]);
    await onAddTags(added);
  };

  const proposedDescription = (suggestion?.description ?? "").trim();
  const descriptionDiffers = proposedDescription !== "" && !sameText(proposedDescription, description ?? "");
  const proposedCategory = suggestion?.category ?? null;
  const proposedTags = (suggestion?.tags ?? []).filter(tag => !tags.includes(tag) && !acceptedTags.includes(tag));
  const confidence = CONFIDENCE_TEXT[suggestion?.confidence ?? "partial"];

  return <div style={{ margin: "6px 0" }}>
    <button type="button" onClick={() => void ask()} disabled={asking || disabled}
      title="Jedno zapytanie do modelu: zaproponuje opis, kategorię i tagi na podstawie nazwy, linków, danych z GitHuba oraz wiedzy modelu o narzędziu. Zna też kategorie i tagi już użyte w radarze. Nic nie zapisze się bez Twojego kliknięcia. Model wybierzesz w sekcji „Model do podpowiadania” nad listą.">
      {asking ? "Myślę…" : "✨ Podpowiedz opis, kategorię i tagi"}</button>
    {error && <span role="alert" className="errorText" style={{ marginLeft: 8, fontSize: ".8rem" }}>{error}</span>}
    {suggestion && <div style={{ marginTop: 6, padding: "8px 10px", background: "#f0fdf4", border: "1px dashed #86efac", borderRadius: 6, fontSize: ".85rem", color: "#334155" }}>
      <div style={{ fontSize: ".78rem" }}>
        <strong>{suggestion.model}</strong> — <span style={{ color: confidence.color }}>{confidence.text}</span>.
        {" "}Odpowiedź pochodzi z wiedzy modelu i może się mylić.
      </div>

      {proposedDescription !== "" && <div style={{ marginTop: 6 }}>
        <strong>Opis:</strong> {proposedDescription}{" "}
        {descriptionDone
          ? <span style={{ color: "#166534" }}>✓ zapisano</span>
          : descriptionDiffers
            ? <button type="button" disabled={disabled} onClick={() => { setDescriptionDone(true); void onUseDescription(proposedDescription); }}>
              {description ? "Zastąp opis" : "Użyj jako opisu"}</button>
            : <span style={{ color: "#64748b" }}>(taki sam jak Twój opis)</span>}
      </div>}

      {proposedCategory && <div style={{ marginTop: 6 }}>
        <strong>Kategoria:</strong>{" "}
        {suggestion.category_changed
          ? <>{category ?? "brak"} → <strong>{proposedCategory}</strong>
            {suggestion.category_is_new && <span title="Takiej kategorii nie ma jeszcze w radarze" style={{ marginLeft: 4, background: "#fef3c7", color: "#92400e", borderRadius: 4, padding: "1px 5px", fontSize: ".72rem" }}>nowa</span>}{" "}
            {categoryDone
              ? <span style={{ color: "#166534" }}>✓ zapisano</span>
              : <button type="button" disabled={disabled} onClick={() => { setCategoryDone(true); void onUseCategory(proposedCategory); }}>Użyj kategorii</button>}</>
          : <span style={{ color: "#64748b" }}>bez zmian ({proposedCategory})</span>}
      </div>}

      {proposedTags.length > 0
        ? <div style={{ marginTop: 6 }}>
          <strong>Tagi:</strong>{" "}
          {proposedTags.map(tag => <button key={tag} type="button" disabled={disabled} style={chip} title="Dodaj jako tag" onClick={() => void addTags([tag])}>+ #{tag}</button>)}
          {proposedTags.length > 1 && <button type="button" disabled={disabled} onClick={() => void addTags(proposedTags)}>Dodaj wszystkie</button>}
        </div>
        : <div style={{ marginTop: 6, color: "#64748b" }}>Brak nowych tagów do zaproponowania.</div>}

      <div style={{ marginTop: 6 }}>
        <button type="button" onClick={() => setSuggestion(null)}>Zamknij</button>
        {suggestion.cost && <span style={{ marginLeft: 8, color: "#64748b", fontSize: ".75rem" }}>koszt: {suggestion.cost} {suggestion.currency ?? ""}</span>}
      </div>
    </div>}
  </div>;
}
