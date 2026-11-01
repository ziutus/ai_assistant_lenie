import React from "react";
import axios from "axios";
import L from "leaflet";
import { GeoJSON, MapContainer, TileLayer } from "react-leaflet";
import { Link, useSearchParams } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";
import { isModelUnavailable, modelOptionText, type ModelOption } from "../utils/modelDetails";

// ADR-033: source-backed world events and directed, versioned relation assessments between countries.
// The map draws only CONFIRMED assessments; proposals (from the LLM or by hand) wait in the queue.

interface Country { id: number; slug: string; name_pl: string; map_code: string; iso3: string | null }
interface Axis { value: string; label: string; scale: Record<string, string> }
interface EventSource { id: number; document_id: number; quote: string; stance: string }
interface GeoEvent {
  id: number; title: string; description: string | null; event_date: string; status: string;
  detection_method: string; model: string | null;
  participants: { country: Country; role: string }[]; sources: EventSource[];
}
interface Assessment {
  id: number; from_country: Country; to_country: Country; axis: string; score: number; confidence: number;
  valid_from: string; valid_to: string | null; review_due_at: string | null; overdue: boolean;
  rationale: string | null; status: string; detection_method: string; version: number;
  evidence?: { event: GeoEvent; stance: string }[];
  other_country?: Country;
  current?: Assessment | null;
}

type Tab = "map" | "proposals" | "events";
const TABS: { value: Tab; label: string }[] = [
  { value: "map", label: "Mapa" },
  { value: "proposals", label: "Propozycje" },
  { value: "events", label: "Zdarzenia" },
];
const ROLE_LABEL: Record<string, string> = { actor: "sprawca", target: "cel", affected: "dotknięty", location: "miejsce" };
const STATUS_LABEL: Record<string, string> = { proposed: "propozycja", confirmed: "zatwierdzone", rejected: "odrzucone" };
const SCORE_COLOR: Record<string, string> = { "-2": "#b91c1c", "-1": "#f97316", "0": "#9ca3af", "1": "#86efac", "2": "#15803d" };
const SCORE_WORD: Record<string, string> = { "-2": "wroga", "-1": "napięta", "0": "neutralna", "1": "przyjazna", "2": "sojusznicza" };
const GEOJSON_URL = "/geo/world-countries.geo.json";
const DEFAULT_PAGE_SIZE = 20;

const errorText = (reason: any) => {
  const data = reason?.response?.data?.message;
  if (data) return data;
  if (reason?.response) return `serwer odpowiedział błędem ${reason.response.status}`;
  if (reason?.request || reason?.message === "Network Error") return "brak odpowiedzi serwera (backend niedostępny, przekroczony czas lub błąd CORS); sprawdź logi backendu";
  return reason?.message || "nieznany błąd";
};
const today = () => new Date().toISOString().slice(0, 10);

const Geopolitics = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.value === params.get("tab"))?.value ?? "map") as Tab;
  const countrySlug = params.get("country") ?? "";
  const at = params.get("at") ?? today();
  const axis = params.get("axis") ?? "political";
  const direction = params.get("direction") === "to" ? "to" : "from";
  const requestedSize = Number(params.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const pageSize = PAGE_SIZES.includes(requestedSize) ? requestedSize : DEFAULT_PAGE_SIZE;
  const requestedPage = Number(params.get("page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const [countries, setCountries] = React.useState<Country[]>([]);
  const [axes, setAxes] = React.useState<Axis[]>([]);
  const [relations, setRelations] = React.useState<Assessment[]>([]);
  const [proposals, setProposals] = React.useState<Assessment[]>([]);
  const [events, setEvents] = React.useState<GeoEvent[]>([]);
  const [eventsTotal, setEventsTotal] = React.useState(0);
  const [geojson, setGeojson] = React.useState<any>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [docId, setDocId] = React.useState("");
  const [models, setModels] = React.useState<ModelOption[]>([]);
  const [defaultModel, setDefaultModel] = React.useState("");
  const [modelSaved, setModelSaved] = React.useState(false);
  const [model, setModel] = React.useState("");
  const [reload, setReload] = React.useState(0);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    setParams(next, { replace: true });
  };

  React.useEffect(() => {
    axios.get(`${apiUrl}/countries`, { headers }).then((r) => setCountries(r.data.countries ?? [])).catch((e) => setError(`Nie udało się pobrać krajów: ${errorText(e)}`));
    axios.get(`${apiUrl}/geopolitics/axes`, { headers }).then((r) => setAxes(r.data.axes ?? [])).catch(() => undefined);
    axios.get(`${apiUrl}/geopolitics/model`, { headers }).then((r) => {
      setModels(r.data.models ?? []);
      setDefaultModel(r.data.default_model ?? "");
      setModelSaved(Boolean(r.data.saved));
      setModel((current) => current || r.data.default_model || "");
    }).catch(() => undefined);
    fetch(GEOJSON_URL).then((r) => r.json()).then(setGeojson).catch(() => undefined);
  }, [apiUrl, headers]);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const done = () => { if (!cancelled) setLoading(false); };
    const fail = (reason: any) => { if (!cancelled) setError(`Nie udało się pobrać danych: ${errorText(reason)}`); };
    if (tab === "map") {
      if (!countrySlug) { setRelations([]); setLoading(false); return () => { cancelled = true; }; }
      axios.get(`${apiUrl}/country_relations`, { headers, params: { country: countrySlug, at, axis, direction } })
        .then((r) => { if (!cancelled) setRelations(r.data.relations ?? []); }).catch(fail).finally(done);
    } else if (tab === "proposals") {
      axios.get(`${apiUrl}/geopolitics/proposals`, { headers })
        .then((r) => { if (!cancelled) setProposals(r.data.proposals ?? []); }).catch(fail).finally(done);
    } else {
      axios.get(`${apiUrl}/geo_events`, { headers, params: { limit: pageSize, offset: (page - 1) * pageSize } })
        .then((r) => { if (!cancelled) { setEvents(r.data.events ?? []); setEventsTotal(r.data.total ?? 0); } }).catch(fail).finally(done);
    }
    return () => { cancelled = true; };
  }, [apiUrl, headers, tab, countrySlug, at, axis, direction, page, pageSize, reload]);

  const decide = async (item: Assessment, decision: "approve" | "reject") => {
    setError(""); setNotice("");
    try {
      await axios.post(`${apiUrl}/geopolitics/proposals/${item.id}/decision`, { decision, expected_version: item.version }, { headers });
      setNotice(decision === "approve" ? "Zatwierdzono. Poprzedni okres relacji został zamknięty." : "Odrzucono propozycję.");
      setReload((n) => n + 1);
    } catch (reason: any) {
      setError(`Nie udało się zapisać decyzji: ${errorText(reason)}`);
    }
  };

  const decideEvent = async (event: GeoEvent, status: "confirmed" | "rejected") => {
    setError(""); setNotice("");
    try {
      await axios.patch(`${apiUrl}/geo_events/${event.id}`, { status }, { headers });
      setReload((n) => n + 1);
    } catch (reason: any) {
      setError(`Nie udało się zmienić zdarzenia: ${errorText(reason)}`);
    }
  };

  const saveDefaultModel = async (value: string | null) => {
    setError(""); setNotice("");
    try {
      const r = await axios.put(`${apiUrl}/geopolitics/model`, { model: value }, { headers });
      setDefaultModel(r.data.default_model ?? "");
      setModelSaved(Boolean(r.data.saved));
      setModel(r.data.default_model ?? "");
      setNotice(value ? "Zapisano domyślny model analizy." : "Przywrócono domyślny model serwera.");
    } catch (reason: any) {
      setError(`Nie udało się zapisać modelu: ${errorText(reason)}`);
    }
  };

  const detect = async (event: React.FormEvent) => {
    event.preventDefault();
    const id = Number(docId);
    if (!Number.isInteger(id) || id <= 0) { setError("Podaj numer dokumentu."); return; }
    setError(""); setNotice(""); setLoading(true);
    try {
      const r = await axios.post(`${apiUrl}/document/${id}/geopolitics/detect`, model ? { model } : {}, { headers, timeout: 180000 });
      const d = r.data;
      const labels: Record<string, string> = {
        quote_not_found: "cytat nie występuje w tekście", bad_date: "nieustalona data",
        bad_participants: "niepoprawni uczestnicy", bad_relation: "niepoprawna relacja",
      };
      const rejected = Object.entries(d.rejected as Record<string, number>).filter(([, n]) => n > 0)
        .map(([key, n]) => `${labels[key] ?? key}: ${n}`).join(", ");
      const cost = d.usage?.llm_cost_amount != null
        ? ` Koszt: ${Number(d.usage.llm_cost_amount).toFixed(4)} ${d.usage.llm_cost_currency ?? ""}${d.usage.llm_cost_status === "estimated" ? " (szacunek)" : ""}, ${d.usage.llm_tokens ?? "?"} tokenów, model ${d.model}.`
        : ` Koszt nieznany (model ${d.model} bez ceny w cenniku).`;
      setNotice(`Dokument ${id}: ${d.events_created} nowych zdarzeń, ${d.events_existing} już znanych, ${d.assessments_proposed} propozycji relacji${d.assessments_merged ? ` (+${d.assessments_merged} dowodów dołączono do istniejących)` : ""}.`
        + (d.dated_from_reference ? ` ${d.dated_from_reference} zdarzeń z datą względną dostało datę artykułu (adnotacja w opisie).` : "")
        + (rejected ? ` Odrzucone przez walidację — ${rejected}.` : "") + cost);
      setReload((n) => n + 1);
    } catch (reason: any) {
      setError(`Analiza dokumentu nie powiodła się: ${errorText(reason)}`);
    } finally {
      setLoading(false);
    }
  };

  const selected = countries.find((c) => c.slug === countrySlug);
  const byMapCode = React.useMemo(() => {
    const map = new Map<string, Assessment>();
    relations.forEach((r) => { if (r.other_country) map.set(r.other_country.map_code, r); });
    return map;
  }, [relations]);

  const style = React.useCallback((feature: any): L.PathOptions => {
    const code = String(feature?.id);
    if (selected && code === selected.map_code) return { fillColor: "#1d4ed8", fillOpacity: 0.7, color: "#1e3a8a", weight: 1.5 };
    const relation = byMapCode.get(code);
    if (!relation) return { fillColor: "#e5e7eb", fillOpacity: 0.35, color: "#94a3b8", weight: 0.6 };
    return { fillColor: SCORE_COLOR[String(relation.score)], fillOpacity: 0.75, color: "#334155", weight: 1, dashArray: relation.overdue ? "4" : undefined };
  }, [selected, byMapCode]);

  const onEachFeature = React.useCallback((feature: any, layer: L.Layer) => {
    const relation = byMapCode.get(String(feature?.id));
    const name = countries.find((c) => c.map_code === String(feature?.id))?.name_pl ?? feature?.properties?.name ?? String(feature?.id);
    const text = relation
      ? `${name}: ${SCORE_WORD[String(relation.score)]} (${relation.score > 0 ? "+" : ""}${relation.score})${relation.overdue ? " · wymaga przeglądu" : ""}`
      : name;
    layer.bindTooltip(text, { sticky: true });
    layer.on("click", () => {
      const slug = countries.find((c) => c.map_code === String(feature?.id))?.slug;
      if (slug) update({ country: slug });
    });
  }, [byMapCode, countries]); // eslint-disable-line react-hooks/exhaustive-deps

  const phrase = (a: Assessment) => direction === "from" ? `${selected?.name_pl} → ${a.other_country?.name_pl}` : `${a.other_country?.name_pl} → ${selected?.name_pl}`;
  const scaleOfAxis = axes.find((a) => a.value === axis)?.scale;

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Geopolityka</h2>
      <p style={{ color: "#667", marginBottom: 10 }}>
        Kierunkowe relacje między państwami i zdarzenia, które je uzasadniają. Mapa pokazuje tylko zatwierdzone oceny; to, co
        zaproponował model albo wpisałeś ręcznie, czeka w „Propozycjach”. Brak koloru oznacza brak danych, nie neutralność.
      </p>
      <div role="tablist" style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {TABS.map((t) => (
          <button key={t.value} role="tab" aria-selected={tab === t.value} className="button"
            style={{ fontWeight: tab === t.value ? 700 : 400, opacity: tab === t.value ? 1 : 0.7 }}
            onClick={() => update({ tab: t.value === "map" ? null : t.value, page: null })}>
            {t.label}{t.value === "proposals" && proposals.length > 0 ? ` (${proposals.length})` : ""}
          </button>
        ))}
      </div>
      {error && <p role="alert" style={{ color: "#a33" }}>{error}</p>}
      {notice && <p role="status" style={{ color: "#166534" }}>{notice}</p>}

      <form onSubmit={detect} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
        <label>Analizuj dokument (nr):{" "}
          <input aria-label="Numer dokumentu" inputMode="numeric" value={docId} onChange={(e) => setDocId(e.target.value)} style={{ width: 90, padding: "4px 8px" }} />
        </label>
        <label>Model:{" "}
          <select aria-label="Model do analizy" value={model} onChange={(e) => setModel(e.target.value)} disabled={loading || models.length === 0}>
            {models.map((option) => (
              <option key={option.id} value={option.id} disabled={isModelUnavailable(option)}>
                {modelOptionText(option)}{option.id === defaultModel ? " — domyślny" : ""}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="button" disabled={!model || (model === defaultModel && modelSaved)}
          onClick={() => saveDefaultModel(model)}>Ustaw jako domyślny</button>
        {modelSaved && <button type="button" className="button" onClick={() => saveDefaultModel(null)}>Przywróć domyślny serwera</button>}
        <button type="submit" className="button" disabled={loading}>Zaproponuj zdarzenia</button>
        <span style={{ color: "#64748b", fontSize: "0.85em" }}>Ceny: wejście / wyjście za 1 mln tokenów. Model tylko proponuje; nic nie trafia na mapę bez Twojej decyzji.</span>
      </form>

      {tab === "map" && (
        <div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 10 }}>
            <label>Kraj:{" "}
              <select aria-label="Kraj" value={countrySlug} onChange={(e) => update({ country: e.target.value || null })}>
                <option value="">— wybierz —</option>
                {countries.map((c) => <option key={c.id} value={c.slug}>{c.name_pl}</option>)}
              </select>
            </label>
            <label>Na dzień:{" "}
              <input type="date" aria-label="Data" value={at} onChange={(e) => update({ at: e.target.value || null })} />
            </label>
            <label>Oś:{" "}
              <select aria-label="Oś" value={axis} onChange={(e) => update({ axis: e.target.value === "political" ? null : e.target.value })}>
                {(axes.length ? axes : [{ value: "political", label: "Polityczna", scale: {} }]).map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
              </select>
            </label>
            <label>Kierunek:{" "}
              <select aria-label="Kierunek" value={direction} onChange={(e) => update({ direction: e.target.value === "from" ? null : e.target.value })}>
                <option value="from">Wybrany kraj wobec innych</option>
                <option value="to">Inni wobec wybranego kraju</option>
              </select>
            </label>
            {loading && <span style={{ color: "#64748b" }}>Wczytuję…</span>}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", fontSize: "0.85em", marginBottom: 8 }} aria-label="Legenda">
            {["-2", "-1", "0", "1", "2"].map((s) => (
              <span key={s}><span style={{ display: "inline-block", width: 12, height: 12, background: SCORE_COLOR[s], marginRight: 4, border: "1px solid #334155" }} />{SCORE_WORD[s]} ({s})</span>
            ))}
            <span><span style={{ display: "inline-block", width: 12, height: 12, background: "#e5e7eb", marginRight: 4, border: "1px solid #94a3b8" }} />brak danych</span>
            <span>linia przerywana = ocena po terminie przeglądu</span>
          </div>
          <div style={{ height: 420, marginBottom: 12, border: "1px solid #e2e8f0", borderRadius: 6, overflow: "hidden" }}>
            <MapContainer center={[25, 10]} zoom={2} minZoom={1} style={{ height: "100%", width: "100%" }} worldCopyJump>
              <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap" opacity={0.35} />
              {geojson && (
                <GeoJSON key={`${countrySlug}|${at}|${axis}|${direction}|${relations.map((r) => `${r.id}:${r.score}`).join(",")}`}
                  data={geojson} style={style} onEachFeature={onEachFeature} />
              )}
            </MapContainer>
          </div>
          {!selected && <p style={{ color: "#667" }}>Wybierz kraj (lub kliknij go na mapie), aby zobaczyć jego relacje.</p>}
          {selected && !loading && relations.length === 0 && (
            <p style={{ color: "#667" }}>Brak zatwierdzonych ocen dla {selected.name_pl} na {at} ({axes.find((a) => a.value === axis)?.label ?? axis}). To brak danych, nie neutralność.</p>
          )}
          <ul aria-label="Relacje" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {relations.map((r) => (
              <li key={r.id} style={{ padding: "8px 10px", marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
                <strong>{phrase(r)}</strong>{" "}
                <span style={{ background: SCORE_COLOR[String(r.score)], padding: "1px 8px", borderRadius: 10, color: Math.abs(r.score) === 2 ? "#fff" : "#111" }}>
                  {SCORE_WORD[String(r.score)]} ({r.score > 0 ? "+" : ""}{r.score})
                </span>{" "}
                <span style={{ color: "#64748b", fontSize: "0.85em" }}>
                  pewność {Math.round(r.confidence * 100)}% · od {r.valid_from}{r.valid_to ? ` do ${r.valid_to}` : ""}
                  {r.overdue ? " · wymaga przeglądu" : ""}
                </span>
                {r.rationale && <div style={{ margin: "4px 0" }}>{r.rationale}</div>}
                <EvidenceList evidence={r.evidence} />
              </li>
            ))}
          </ul>
          {scaleOfAxis && Object.keys(scaleOfAxis).length > 0 && (
            <details style={{ marginTop: 8 }}>
              <summary>Co znaczą oceny na tej osi</summary>
              <ul>{Object.entries(scaleOfAxis).map(([score, text]) => <li key={score}><strong>{score}</strong>: {text}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      {tab === "proposals" && (
        <div>
          {!loading && proposals.length === 0 && <p style={{ color: "#667" }}>Brak propozycji do rozpatrzenia.</p>}
          <ul aria-label="Propozycje" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {proposals.map((p) => (
              <li key={p.id} style={{ padding: "8px 10px", marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
                <strong>{p.from_country.name_pl} → {p.to_country.name_pl}</strong>{" "}
                <span style={{ color: "#64748b", fontSize: "0.85em" }}>
                  {axes.find((a) => a.value === p.axis)?.label ?? p.axis} · od {p.valid_from} · pewność {Math.round(p.confidence * 100)}%
                  {p.detection_method === "llm" ? " · zaproponował model" : " · wpisane ręcznie"}
                </span>
                <div style={{ margin: "4px 0" }}>
                  Proponowana ocena: <strong>{SCORE_WORD[String(p.score)]} ({p.score > 0 ? "+" : ""}{p.score})</strong>
                  {" — "}{p.current
                    ? <>obecnie: {SCORE_WORD[String(p.current.score)]} ({p.current.score > 0 ? "+" : ""}{p.current.score}) od {p.current.valid_from}; zatwierdzenie zamknie ten okres</>
                    : "to byłaby pierwsza zatwierdzona ocena tej pary"}
                </div>
                {p.rationale && <div style={{ margin: "4px 0" }}>{p.rationale}</div>}
                <EvidenceList evidence={p.evidence} />
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                  <button className="button" onClick={() => decide(p, "approve")}>Zatwierdź zdarzenie i zmianę</button>
                  <button className="button" onClick={() => decide(p, "reject")}>Odrzuć</button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {tab === "events" && (
        <div>
          <span style={{ color: "#64748b" }}>{loading ? "Wczytuję…" : `${eventsTotal} zdarzeń`}</span>
          <ul aria-label="Zdarzenia" style={{ listStyle: "none", padding: 0, margin: "6px 0 0" }}>
            {events.map((e) => (
              <li key={e.id} style={{ padding: "8px 10px", marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
                <strong>📅 {e.event_date} — {e.title}</strong>{" "}
                <span style={{ color: "#64748b", fontSize: "0.85em" }}>{STATUS_LABEL[e.status] ?? e.status}{e.detection_method === "llm" ? " · model" : ""}</span>
                {e.description && <div style={{ margin: "4px 0" }}>{e.description}</div>}
                <div style={{ fontSize: "0.85em", color: "#475569" }}>
                  {e.participants.map((p) => `${p.country.name_pl} (${ROLE_LABEL[p.role] ?? p.role})`).join(", ")}
                </div>
                <SourceList sources={e.sources} />
                {e.status === "proposed" && (
                  <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                    <button className="button" onClick={() => decideEvent(e, "confirmed")}>Zatwierdź zdarzenie</button>
                    <button className="button" onClick={() => decideEvent(e, "rejected")}>Odrzuć</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={pageSize} total={eventsTotal} isLoading={loading} label="zdarzeń"
            onPageChange={(next) => update({ page: next > 1 ? String(next) : null })} />
        </div>
      )}
    </div>
  );
};

const SourceList = ({ sources }: { sources: EventSource[] }) => (
  sources.length === 0 ? null : (
    <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: "0.85em" }}>
      {sources.map((s) => (
        <li key={s.id}>
          <Link to={`/read/${s.document_id}`}>Dokument {s.document_id}</Link>
          {s.stance === "disputes" ? " (podważa)" : ""}: „{s.quote}”
        </li>
      ))}
    </ul>
  )
);

const EvidenceList = ({ evidence }: { evidence?: { event: GeoEvent; stance: string }[] }) => (
  !evidence || evidence.length === 0 ? (
    <div style={{ color: "#94a3b8", fontSize: "0.85em" }}>Bez powiązanych zdarzeń.</div>
  ) : (
    <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: "0.85em" }}>
      {evidence.map(({ event, stance }) => (
        <li key={event.id}>
          {event.event_date}: {event.title}{stance === "contradicts" ? " (przeczy)" : ""}
          <SourceList sources={event.sources} />
        </li>
      ))}
    </ul>
  )
);

export default Geopolitics;
