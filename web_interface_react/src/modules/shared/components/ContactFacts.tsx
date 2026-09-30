import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";

type Assertion = {
  id: number; source_key: string; value: Record<string, unknown>;
  status: "candidate" | "confirmed" | "rejected"; observed_at: string | null;
  last_seen_at?: string | null; source_url?: string | null; evidence_note?: string | null;
  review_note?: string | null; reviewed_by?: string | null; reviewed_at?: string | null;
};
type Slot = {
  id: number; attribute_key: string; resolution_mode: "auto" | "pinned" | "suppressed";
  selected_assertion_id: number | null; assertions: Assertion[];
};
const attributes: Record<string, string> = {
  birthday: "Data urodzenia", gender: "Płeć", current_city: "Obecne miasto",
  hometown: "Miejscowość rodzinna", education: "Wykształcenie",
};
const sources: Record<string, string> = {
  facebook: "Facebook", linkedin: "LinkedIn", user_manual: "Ręcznie (użytkownik)",
  legacy_unknown: "Dane sprzed śledzenia źródeł",
};
const statuses = { candidate: "Kandydat", confirmed: "Potwierdzona", rejected: "Odrzucona" };
const colors = { candidate: "#fff8e6", confirmed: "#ecfdf5", rejected: "#fee2e2" };
const order = ["birthday", "gender", "current_city", "hometown"];
const rank = (key: string) => order.includes(key) ? order.indexOf(key) : order.length;
const timestamp = (value: string | null) => value ? Date.parse(value) || 0 : 0;
const date = (value?: string | null, full = false) => {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return full ? parsed.toLocaleString("pl-PL") : parsed.toLocaleDateString("pl-PL");
};
const valueText = (key: string, value: Assertion["value"]) => {
  if (key === "birthday") {
    const part = (value: unknown) => value == null ? "??" : String(value).padStart(2, "0");
    if (value.day == null && value.month == null) return value.year == null ? "-" : `${value.year} (bez dnia i miesiąca)`;
    return `${part(value.day)}.${part(value.month)}${value.year == null ? " (bez roku)" : `.${value.year}`}`;
  }
  if (key === "gender") return ({ male: "mężczyzna", female: "kobieta", other: "inna" } as Record<string, string>)[String(value.gender)] ?? String(value.gender ?? "-");
  if (value[key] != null) return String(value[key]);
  return Object.values(value).filter(v => v != null && v !== "").map(v =>
    typeof v === "object" ? JSON.stringify(v) : String(v)).join(" · ") || "-";
};

export default function ContactFacts({ contactId, editable, onChanged }: {
  contactId: string; editable: boolean; onChanged: () => void;
}) {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [slots, setSlots] = React.useState<Slot[]>([]);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [rejectId, setRejectId] = React.useState<number | null>(null);
  const [note, setNote] = React.useState("");
  const base = `${apiUrl}/contacts/${contactId}/facts`;
  const load = React.useCallback(async () => {
    const response = await axios.get(base, { headers: { "x-api-key": `${apiKey}` } });
    return response.data.facts as Slot[];
  }, [base, apiKey]);
  React.useEffect(() => {
    let active = true;
    setSlots([]); setError(""); setRejectId(null); setNote("");
    void load().then(facts => { if (active) setSlots(facts); }).catch(() => {
      if (active) setError("Nie udało się pobrać faktów i źródeł.");
    });
    return () => { active = false; };
  }, [load]);
  React.useEffect(() => { setRejectId(null); setNote(""); }, [editable]);
  const review = async (id: number, status: Assertion["status"], reason?: string) => {
    setBusy(true); setError("");
    try {
      await axios.patch(`${base}/assertions/${id}`, { status, ...(reason?.trim() ? { note: reason.trim() } : {}) },
        { headers: { "x-api-key": `${apiKey}` } });
      setRejectId(null); setNote("");
      try { setSlots(await load()); }
      finally { onChanged(); }
    } catch {
      setError("Nie udało się zapisać lub odświeżyć faktów i źródeł. Spróbuj ponownie.");
    } finally { setBusy(false); }
  };
  const rows = slots.flatMap(slot => slot.assertions.map(assertion => ({ slot, assertion }))).sort((a, b) =>
    rank(a.slot.attribute_key) - rank(b.slot.attribute_key)
    || a.slot.attribute_key.localeCompare(b.slot.attribute_key, "pl")
    || Number(b.assertion.id === b.slot.selected_assertion_id) - Number(a.assertion.id === a.slot.selected_assertion_id)
    || timestamp(b.assertion.observed_at) - timestamp(a.assertion.observed_at)
    || b.assertion.id - a.assertion.id);
  const rejected = rows.filter(({ assertion }) => assertion.status === "rejected").length;
  if (!rows.length && !error) return null;
  return <section style={{ marginTop: 20 }} aria-label="Fakty i źródła">
    <h3>Fakty i źródła</h3>
    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    {!!rows.length && <>
      <p>Tez: {rows.length}{rejected > 0 && `, odrzuconych: ${rejected}`}</p>
      <div className="contact-merge-scroll" tabIndex={0} role="region" aria-label="Tabela faktów i źródeł">
        <table className="contact-merge-table" style={{ minWidth: 1100, tableLayout: "auto" }}>
          <thead><tr>{["Atrybut", "Źródło", "Wartość", "Status", "Powód / uwagi", "Widoczna", "Zaobserwowano", "Przegląd"].map(label =>
            <th scope="col" key={label}>{label}</th>)}</tr></thead>
          <tbody>{rows.map(({ slot, assertion: a }) => <tr key={a.id}>
            <td>{attributes[slot.attribute_key] ?? slot.attribute_key}</td>
            <td>{a.source_url ? <a href={a.source_url} target="_blank" rel="noopener noreferrer">{sources[a.source_key] ?? a.source_key}</a> : sources[a.source_key] ?? a.source_key}</td>
            <td>{valueText(slot.attribute_key, a.value)}</td>
            <td><span style={{ background: colors[a.status], color: a.status === "rejected" ? "#b91c1c" : "#333", borderRadius: 12, padding: "2px 8px" }}>{statuses[a.status]}</span></td>
            <td>{a.evidence_note && <div>{a.evidence_note}</div>}{a.review_note && <div>Przegląd: {a.review_note}</div>}{!a.evidence_note && !a.review_note && "-"}</td>
            <td>{a.id === slot.selected_assertion_id ? <><strong>✓ Widoczna</strong><br /><small>{slot.resolution_mode === "pinned" ? "przypięta" : "automatyczna"}</small></> : "-"}</td>
            <td title={`Zaobserwowano: ${date(a.observed_at, true)}; Ostatnio widziano: ${date(a.last_seen_at, true)}`}>{date(a.observed_at)}</td>
            <td>{[a.reviewed_by, a.reviewed_at ? date(a.reviewed_at, true) : null].filter(Boolean).join(" · ") || "-"}
              {a.source_key === "user_manual" ? <div><small title="Wartość wpisana ręcznie - edytuj pole kontaktu">Wartość wpisana ręcznie</small></div> : editable && <div>
                {a.status !== "confirmed" && <button type="button" disabled={busy} onClick={() => void review(a.id, "confirmed")}>Potwierdź</button>}
                {a.status !== "rejected" && <button type="button" disabled={busy} onClick={() => { setRejectId(a.id); setNote(""); }}>Odrzuć...</button>}
                {a.status !== "candidate" && <button type="button" disabled={busy} onClick={() => void review(a.id, "candidate")}>Otwórz ponownie</button>}
                {rejectId === a.id && <fieldset disabled={busy}>
                  <label>Powód odrzucenia <input autoFocus maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></label>
                  <button type="button" onClick={() => void review(a.id, "rejected", note)}>Zapisz odrzucenie</button>
                  <button type="button" onClick={() => setRejectId(null)}>Anuluj</button>
                </fieldset>}
              </div>}
            </td>
          </tr>)}</tbody>
        </table>
      </div>
    </>}
  </section>;
}
