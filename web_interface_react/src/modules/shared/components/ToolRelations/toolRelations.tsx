import React from "react";

export type ToolRelation = {
  id: number;
  relation: "works_with" | "emulates" | "alternative_to";
  direction: "out" | "in";
  status: "proposed" | "confirmed";
  context: string | null;
  other_id: number;
  other_name: string;
  other_status: string;
  in_my_stack: boolean;
};

// The same edge reads differently from each end: Floci emulates AWS, AWS is emulated by Floci.
const labels: Record<ToolRelation["relation"], Record<ToolRelation["direction"], string>> = {
  works_with: { out: "współpracuje z", in: "współpracuje z" },
  alternative_to: { out: "alternatywa dla", in: "ma alternatywę" },
  emulates: { out: "emuluje", in: "emulowane przez" },
};

export const relationLabel = (relation: ToolRelation) => labels[relation.relation][relation.direction];

type Props = {
  relations: ToolRelation[];
  onReview: (id: number, status: "confirmed" | "rejected") => void;
};

export default function ToolRelations({ relations, onReview }: Props) {
  if (!relations.length) return null;
  return <div style={{ margin: "8px 0", fontSize: ".85rem", display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
    {relations.map(relation => <span key={relation.id}
      title={`${relationLabel(relation)} ${relation.other_name}${relation.status === "proposed" ? " — propozycja wykryta automatycznie" : ""}${relation.context ? `: …${relation.context}…` : ""}`}
      style={{ border: relation.status === "proposed" ? "1px dashed #94a3b8" : "1px solid #94a3b8", background: relation.in_my_stack ? "#dcfce7" : "#f1f5f9", color: "#334155", borderRadius: 12, padding: "2px 8px" }}>
      {relationLabel(relation)} <strong>{relation.other_name}</strong>{relation.in_my_stack && " ✔ mój stack"}
      {relation.status === "proposed" && <>
        {" "}<button type="button" aria-label={`Potwierdź powiązanie z ${relation.other_name}`} title="Potwierdź" onClick={() => onReview(relation.id, "confirmed")} style={{ padding: "0 4px" }}>✓</button>
        <button type="button" aria-label={`Odrzuć powiązanie z ${relation.other_name}`} title="Odrzuć — nie zostanie zaproponowane ponownie" onClick={() => onReview(relation.id, "rejected")} style={{ padding: "0 4px" }}>✗</button>
      </>}
    </span>)}
  </div>;
}
