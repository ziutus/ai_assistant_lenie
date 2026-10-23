import React from "react";
import type { GithubStats } from "../GithubStatsLine/githubStatsLine";

// Same shape as the stored tags: lowercase, inner spaces to "-".
export const toTag = (value: string) => value.trim().toLowerCase().split(/\s+/).join("-");
const sameText = (a: string, b: string) => a.trim().replace(/\s+/g, " ").toLowerCase() === b.trim().replace(/\s+/g, " ").toLowerCase();

const chip: React.CSSProperties = { background: "#dcfce7", color: "#166534", border: "1px dashed #16a34a", borderRadius: 999, padding: "2px 8px", fontSize: ".75rem", cursor: "pointer" };

/**
 * The repository's own "About" (description and topics) as a hint next to the entry's data: nothing is
 * written until a button is clicked. Topics that are already tags are shown as such, not offered again.
 */
export default function GithubAbout({ stats, ownDescription, tags, disabled, onUseDescription, onAddTags }: {
  stats: GithubStats; ownDescription: string | null; tags: string[]; disabled: boolean;
  onUseDescription: (text: string) => void; onAddTags: (topics: string[]) => void;
}) {
  const description = (stats.description ?? "").trim();
  const topics = Array.from(new Set((stats.topics ?? []).map(toTag).filter(Boolean)));
  if (!description && !topics.length) return null;
  const missing = topics.filter(topic => !tags.includes(topic));
  const differs = description !== "" && !sameText(description, ownDescription ?? "");
  return <div style={{ margin: "6px 0", padding: "6px 10px", background: "#f8fafc", borderLeft: "3px solid #94a3b8", borderRadius: 4, fontSize: ".85rem", color: "#475569" }}
    title="Dane pomocnicze z GitHuba; nic nie zapisze się bez kliknięcia.">
    {description && <div>
      <strong>Z GitHuba:</strong> {description}{" "}
      {differs && <button type="button" disabled={disabled} onClick={() => onUseDescription(description)}
        title={ownDescription ? "Zastąpi dotychczasowy opis opisem z GitHuba" : "Zapisze opis z GitHuba jako opis tego wpisu"}>
        {ownDescription ? "Zastąp opis tym z GitHuba" : "Użyj jako opisu"}</button>}
      {!differs && ownDescription && <span style={{ color: "#64748b" }}>(taki sam jak Twój opis)</span>}
    </div>}
    {topics.length > 0 && <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
      <strong>Tematy:</strong>
      {topics.map(topic => tags.includes(topic)
        ? <span key={topic} title="Już jest wśród tagów" style={{ ...chip, background: "#e2e8f0", color: "#475569", border: "1px solid #cbd5e1", cursor: "default" }}>✓ #{topic}</span>
        : <button key={topic} type="button" disabled={disabled} onClick={() => onAddTags([topic])} style={chip} title="Dodaj jako tag">+ #{topic}</button>)}
      {missing.length > 1 && <button type="button" disabled={disabled} onClick={() => onAddTags(missing)}>Dodaj wszystkie ({missing.length})</button>}
    </div>}
  </div>;
}
