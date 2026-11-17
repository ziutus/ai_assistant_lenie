import React from "react";
import axios from "axios";
import { COUNTRY_SLUG_TO_ISO3 } from "../../data/countryIso";
import { ISO3_TO_NAME_PL } from "../../data/countryNames";

// "Kraje i regiony" of a registry person (GET/POST/DELETE /persons/:id/territories): the countries (kraj-* tag slug)
// and geopolitical macro-regions (miejsce-* tag slug, e.g. Bliski Wschód) the person is tied to, each with the kind
// of tie and optional dates of the role. The ties are what lets a document about Yemen offer "the people of Yemen"
// when choosing between namesakes and repairing a mangled name. Candidates come from the person's own documents
// and are never attached automatically.

export type TerritoryTie = {
  id: number; kind: "country" | "region"; slug: string; name_pl: string; tag: string;
  relation: string; relation_label: string; note: string | null; valid_from: string | null; valid_to: string | null;
};
type Suggestion = { kind: "country" | "region"; slug: string; name_pl: string; documents: number };
type RegionOption = { slug: string; name_pl: string };

const FALLBACK_RELATIONS: Record<string, string> = {
  citizen_of: "obywatelstwo", holds_office_in: "pełni funkcję w", active_in: "działa w", linked_to: "powiązanie",
};

const COUNTRY_OPTIONS = Object.entries(COUNTRY_SLUG_TO_ISO3)
  .map(([slug, iso]) => ({ slug, name: ISO3_TO_NAME_PL[iso] ?? slug }))
  .sort((a, b) => a.name.localeCompare(b.name, "pl"));

const errorText = (failure: unknown, fallback: string) => {
  const err = failure as { response?: { data?: { message?: string } }; message?: string };
  return err.response?.data?.message ?? err.message ?? fallback;
};

const period = (tie: TerritoryTie) => {
  if (tie.valid_from && tie.valid_to) return `${tie.valid_from} – ${tie.valid_to}`;
  if (tie.valid_from) return `od ${tie.valid_from}`;
  if (tie.valid_to) return `do ${tie.valid_to}`;
  return "";
};

const PersonTerritories = ({ personId, apiUrl, apiKey }: { personId: number; apiUrl: string; apiKey: string }) => {
  const [ties, setTies] = React.useState<TerritoryTie[]>([]);
  const [suggestions, setSuggestions] = React.useState<Suggestion[]>([]);
  const [relations, setRelations] = React.useState<Record<string, string>>(FALLBACK_RELATIONS);
  const [regions, setRegions] = React.useState<RegionOption[]>([]);
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState("");
  const [kind, setKind] = React.useState<"country" | "region">("country");
  const [slug, setSlug] = React.useState("");
  const [relation, setRelation] = React.useState("citizen_of");
  const [validFrom, setValidFrom] = React.useState("");
  const [validTo, setValidTo] = React.useState("");
  const [note, setNote] = React.useState("");

  const headers = React.useMemo(() => ({ "x-api-key": apiKey, "Content-Type": "application/json" }), [apiKey]);

  const load = React.useCallback(async () => {
    try {
      const response = await axios.get(`${apiUrl}/persons/${personId}/territories`, { headers });
      const data = response.data ?? {};
      setTies(data.territories ?? []);
      setSuggestions(data.suggestions ?? []);
      setRelations(data.relations ?? FALLBACK_RELATIONS);
      setRegions(data.regions ?? []);
      setError("");
    } catch (failure) {
      setError(errorText(failure, "Nie udało się pobrać krajów i regionów osoby."));
    } finally {
      setLoaded(true);
    }
  }, [apiUrl, headers, personId]);

  React.useEffect(() => { void load(); }, [load]);

  const add = async (body: { kind: string; slug: string; relation: string; note?: string; valid_from?: string; valid_to?: string }) => {
    setError("");
    try {
      await axios.post(`${apiUrl}/persons/${personId}/territories`, body, { headers });
      setSlug(""); setNote(""); setValidFrom(""); setValidTo("");
      await load();
    } catch (failure) {
      setError(`Nie udało się dodać: ${errorText(failure, "błąd zapisu")}`);
    }
  };

  const remove = async (tie: TerritoryTie) => {
    setError("");
    try {
      await axios.delete(`${apiUrl}/persons/${personId}/territories/${tie.id}`, { headers });
      await load();
    } catch (failure) {
      setError(`Nie udało się usunąć: ${errorText(failure, "błąd zapisu")}`);
    }
  };

  const options = kind === "country"
    ? COUNTRY_OPTIONS.map((country) => ({ slug: country.slug, name: country.name }))
    : regions.map((region) => ({ slug: region.slug, name: region.name_pl }));

  return (
    <section aria-label="Kraje i regiony osoby" style={{ marginTop: 12 }}>
      <h3 style={{ margin: "0 0 6px" }}>Kraje i regiony ({ties.length})</h3>
      <div style={{ fontSize: "0.8em", color: "#667", marginBottom: 4 }}>
        Powiązanie z krajem lub regionem pomaga w dokumentach o tym obszarze: wybrać właściwą osobę spośród imienników
        i poprawić przekręcone nazwisko.
      </div>
      {error && <div role="alert" style={{ color: "#b91c1c", marginBottom: 4 }}>{error}</div>}
      {loaded && !error && ties.length === 0 && <div style={{ color: "#667", fontSize: "0.9em" }}>Brak powiązań.</div>}
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {ties.map((tie) => (
          <li key={tie.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "2px 0", flexWrap: "wrap" }}>
            <span aria-hidden="true">{tie.kind === "country" ? "🌍" : "🗺️"}</span>
            <strong>{tie.name_pl}</strong>
            <span style={{ color: "#0369a1", fontSize: "0.85em" }}>{tie.relation_label}</span>
            {period(tie) && <span style={{ color: "#667", fontSize: "0.85em" }}>({period(tie)})</span>}
            {tie.note && <span style={{ color: "#667", fontSize: "0.85em" }}>— {tie.note}</span>}
            <button type="button" onClick={() => void remove(tie)} title="Usuń powiązanie" aria-label={`Usuń ${tie.name_pl}: ${tie.relation_label}`}
              style={{ border: "none", background: "none", color: "#a33", cursor: "pointer" }}>✕</button>
          </li>
        ))}
      </ul>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 6 }}>
        <select aria-label="Rodzaj obszaru" value={kind} onChange={(e) => { setKind(e.target.value as "country" | "region"); setSlug(""); }}>
          <option value="country">Kraj</option>
          <option value="region">Region</option>
        </select>
        <select aria-label="Obszar" value={slug} onChange={(e) => setSlug(e.target.value)} style={{ minWidth: 200 }}>
          <option value="">{kind === "country" ? "— wybierz kraj —" : "— wybierz region —"}</option>
          {options.map((option) => <option key={option.slug} value={option.slug}>{option.name}</option>)}
        </select>
        <select aria-label="Rodzaj powiązania" value={relation} onChange={(e) => setRelation(e.target.value)}>
          {Object.entries(relations).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <label>od <input type="date" aria-label="Od" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} /></label>
        <label>do <input type="date" aria-label="Do" value={validTo} onChange={(e) => setValidTo(e.target.value)} /></label>
        <input type="text" aria-label="Notatka do powiązania" placeholder="Notatka (opcjonalnie)" value={note}
          onChange={(e) => setNote(e.target.value)} style={{ minWidth: 180 }} />
        <button type="button" className={"button"} disabled={!slug} onClick={() => void add({
          kind, slug, relation, note: note.trim() || undefined, valid_from: validFrom || undefined, valid_to: validTo || undefined,
        })}>Dodaj powiązanie</button>
      </div>
      {suggestions.length > 0 && (
        <div style={{ marginTop: 6, fontSize: "0.85em", color: "#667" }}>
          Obszary z dokumentów tej osoby (kliknij, by dodać wybranym rodzajem powiązania):{" "}
          {suggestions.map((suggestion) => (
            <button key={`${suggestion.kind}:${suggestion.slug}`} type="button"
              onClick={() => void add({ kind: suggestion.kind, slug: suggestion.slug, relation })}
              title={`Dodaj: ${relations[relation] ?? relation} ${suggestion.name_pl}`}
              style={{ marginRight: 6, padding: "1px 8px", border: "1px solid #cbd5e1", borderRadius: 10, background: "#f8fafc", color: "#334155", cursor: "pointer" }}>
              + {suggestion.name_pl} ×{suggestion.documents}
            </button>
          ))}
        </div>
      )}
    </section>
  );
};

export default PersonTerritories;
