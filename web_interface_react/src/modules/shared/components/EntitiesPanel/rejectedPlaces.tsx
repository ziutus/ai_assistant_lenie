import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";
import type { EntityItem } from "./entitiesPanel";

export default function RejectedPlaces({ docId, items }: { docId: string | number; items: EntityItem[] }) {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [open, setOpen] = React.useState(false);
  const [decisions, setDecisions] = React.useState<{ entity_text: string; rationale: string | null }[]>([]);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    if (!open) return;
    let active = true;
    axios.get(`${apiUrl}/ner_context_decisions`, {
      headers: { "x-api-key": apiKey ?? "" },
      params: { document_id: docId, entity_type: "placeName", limit: 200, latest_only: true },
    }).then(response => { if (active) setDecisions(response.data.items); })
      .catch(() => { if (active) setError("Nie udało się pobrać uzasadnień klasyfikatora."); });
    return () => { active = false; };
  }, [open, docId, apiUrl, apiKey]);
  if (!items.length) return null;
  return <details onToggle={event => { if (event.currentTarget.open) setOpen(true); }}>
    <summary>Odrzucone miejsca ({items.length})</summary>
    {error && <small style={{ color: "#b91c1c" }}>{error}</small>}
    <ul>{items.map(item => {
      const names = [item.text, ...(item.variants ?? [])].map(name => name.toLocaleLowerCase("pl"));
      const decision = decisions.find(row => names.includes(row.entity_text.toLocaleLowerCase("pl")));
      const reason = item.place_review_reason === "context_not_place"
        ? "odrzucone automatycznie przez klasyfikator kontekstu"
        : item.place_review_reason === "rejected_by_user" ? "odrzucone ręcznie" : item.place_review_reason;
      return <li key={item.id ?? item.text}><strong>{item.text}</strong>: {reason}
        {decision?.rationale && <p>{decision.rationale}</p>}</li>;
    })}</ul>
    <Link to={`/ner-decisions?document_id=${docId}`}>Wszystkie decyzje automatyczne tego dokumentu</Link>
  </details>;
}
