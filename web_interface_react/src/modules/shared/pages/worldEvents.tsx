import React from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";
import WorldEventCard, {
  errorText, type CountryRef, type Kind, type Role, type WorldEvent,
} from "../components/WorldEventCard/worldEventCard";

// ADR-034: the registry of world events. An event may have no country and no date (an outage, a product
// launch, a pandemic declared by WHO), several names, and is told apart from a mere NAME that a reader marked
// in a document (a named-event mention): a name only SUGGESTS an event, the reader links it.

type Tab = "events" | "unlinked";

interface Suggestion { reason: string; score: number; event: { id: number; title: string; kind: string; event_date: string | null; status: string } }
interface MentionGroup {
  name_key: string; name: string; description: string | null; mentions: number; document_count: number;
  documents: { id: number; title: string | null; mentions: number; entity_id: number }[];
  suggestions: Suggestion[];
}

const DEFAULT_PAGE_SIZE = 25;

const WorldEvents = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "unlinked" ? "unlinked" : "events";
  const q = params.get("q") ?? "";
  const kind = params.get("kind") ?? "";
  const withCountries = params.get("with_countries") ?? "";
  const country = params.get("country") ?? "";
  const status = params.get("status") ?? "";
  const requestedSize = Number(params.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const pageSize = PAGE_SIZES.includes(requestedSize) ? requestedSize : DEFAULT_PAGE_SIZE;
  const requestedPage = Number(params.get("page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const [kinds, setKinds] = React.useState<Kind[]>([]);
  const [roles, setRoles] = React.useState<Role[]>([]);
  const [countries, setCountries] = React.useState<CountryRef[]>([]);
  const [events, setEvents] = React.useState<WorldEvent[]>([]);
  const [mentions, setMentions] = React.useState<MentionGroup[]>([]);
  const [total, setTotal] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [reload, setReload] = React.useState(0);
  const [queryText, setQueryText] = React.useState(q);
  const [form, setForm] = React.useState({ title: "", kind: "other", event_date: "", event_date_end: "", is_ongoing: false, description: "", aliases: "" });

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    setParams(next, { replace: true });
  };
  const message = (text: string, isError = false) => { if (isError) { setError(text); setNotice(""); } else { setNotice(text); setError(""); } };
  const refresh = () => setReload((n) => n + 1);

  React.useEffect(() => {
    axios.get(`${apiUrl}/geo_event_kinds`, { headers }).then((r) => setKinds(r.data.kinds ?? [])).catch(() => undefined);
    axios.get(`${apiUrl}/geo_event_roles`, { headers }).then((r) => setRoles(r.data.roles ?? [])).catch(() => undefined);
    axios.get(`${apiUrl}/countries`, { headers }).then((r) => setCountries(r.data.countries ?? [])).catch(() => undefined);
  }, [apiUrl, headers]);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const paging = { limit: pageSize, offset: (page - 1) * pageSize };
    const request = tab === "events"
      ? axios.get(`${apiUrl}/world_events`, { headers, params: { ...(q && { q }), ...(kind && { kind }), ...(withCountries && { with_countries: withCountries }), ...(country && { country }), ...(status && { status }), ...paging } })
      : axios.get(`${apiUrl}/world_events/unlinked`, { headers, params: { ...(q && { q }), ...paging } });
    request
      .then((r) => {
        if (cancelled) return;
        setTotal(r.data.total ?? 0);
        if (tab === "events") setEvents(r.data.events ?? []); else setMentions(r.data.mentions ?? []);
      })
      .catch((reason) => { if (!cancelled) setError(`Nie udało się pobrać danych: ${errorText(reason)}`); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [apiUrl, headers, tab, q, kind, withCountries, country, status, page, pageSize, reload]);

  const addEvent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) { message("Podaj nazwę zdarzenia.", true); return; }
    try {
      const r = await axios.post(`${apiUrl}/geo_events`, {
        title: form.title, kind: form.kind, description: form.description || undefined,
        event_date: form.event_date || undefined, event_date_end: form.event_date_end || undefined,
        is_ongoing: form.is_ongoing, status: "confirmed",
        aliases: form.aliases.split(",").map((s) => s.trim()).filter(Boolean),
      }, { headers });
      message(r.data.created ? "Dodano zdarzenie." : "Takie zdarzenie już jest w rejestrze; dodano nazwy i źródła.");
      setForm({ title: "", kind: "other", event_date: "", event_date_end: "", is_ongoing: false, description: "", aliases: "" });
      refresh();
    } catch (reason: any) {
      message(`Nie udało się dodać zdarzenia: ${errorText(reason)}`, true);
    }
  };

  const decide = async (path: string, body: Record<string, unknown>, success: string) => {
    try {
      await axios.post(`${apiUrl}/world_events/${path}`, body, { headers });
      message(success);
      refresh();
    } catch (reason: any) {
      message(`Nie udało się zapisać: ${errorText(reason)}`, true);
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Wydarzenia świata</h2>
      <p style={{ color: "#667", marginBottom: 10 }}>
        Rejestr zdarzeń z datą (albo bez niej), z krajami, organizacjami i osobami (albo bez nich), z kilkoma nazwami i dokumentami, które o nich mówią.
        Nazwa zaznaczona w tekście tylko <strong>podpowiada</strong> zdarzenie — powiązanie zatwierdzasz Ty.
        Zdarzenia z krajami zasilają <Link to="/geopolitics?tab=events">Geopolitykę</Link>. To nie są prywatne wydarzenia z książki kontaktów (<Link to="/contact-events">Wydarzenia</Link>).
      </p>
      <div role="tablist" style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button role="tab" aria-selected={tab === "events"} className="button" style={{ fontWeight: tab === "events" ? 700 : 400 }}
          onClick={() => update({ tab: null, page: null })}>Zdarzenia</button>
        <button role="tab" aria-selected={tab === "unlinked"} className="button" style={{ fontWeight: tab === "unlinked" ? 700 : 400 }}
          onClick={() => update({ tab: "unlinked", page: null })}>Do powiązania z tekstów</button>
      </div>
      {error && <p role="alert" style={{ color: "#a33" }}>{error}</p>}
      {notice && <p role="status" style={{ color: "#166534" }}>{notice}</p>}

      <form onSubmit={(e) => { e.preventDefault(); update({ q: queryText.trim() || null, page: null }); }}
        style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 8 }}>
        <input type="search" aria-label="Szukaj zdarzenia" placeholder="Szukaj po nazwie…" value={queryText}
          onChange={(e) => setQueryText(e.target.value)} style={{ padding: "4px 8px" }} />
        {tab === "events" && <>
          <select aria-label="Rodzaj zdarzenia" value={kind} onChange={(e) => update({ kind: e.target.value || null, page: null })}>
            <option value="">Wszystkie rodzaje</option>
            {kinds.map((k) => <option key={k.code} value={k.code}>{k.label}</option>)}
          </select>
          <select aria-label="Kraje" value={withCountries} onChange={(e) => update({ with_countries: e.target.value || null, page: null })}>
            <option value="">Z krajami i bez</option>
            <option value="1">Tylko z krajami</option>
            <option value="0">Tylko bez krajów</option>
          </select>
          <select aria-label="Kraj" value={country} onChange={(e) => update({ country: e.target.value || null, page: null })}>
            <option value="">Wszystkie kraje</option>
            {countries.map((c) => <option key={c.slug} value={c.slug}>{c.name_pl}</option>)}
          </select>
          <select aria-label="Status zdarzenia" value={status} onChange={(e) => update({ status: e.target.value || null, page: null })}>
            <option value="">Wszystkie statusy</option>
            <option value="confirmed">Zatwierdzone</option>
            <option value="proposed">Propozycje (niezatwierdzone)</option>
            <option value="rejected">Odrzucone</option>
          </select>
        </>}
        <button type="submit" className="button">Szukaj</button>
        <span style={{ color: "#64748b" }}>{loading ? "Wczytuję…" : tab === "events" ? `${total} zdarzeń` : `${total} nazw do powiązania`}</span>
      </form>

      {tab === "events" && (
        <>
          <details style={{ marginBottom: 10 }}>
            <summary>➕ Dodaj zdarzenie</summary>
            <form onSubmit={addEvent} aria-label="Nowe zdarzenie" style={{ display: "grid", gap: 6, maxWidth: 560, padding: 8 }}>
              <label>Nazwa <input aria-label="Nazwa nowego zdarzenia" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} style={{ width: "100%" }} /></label>
              <label>Rodzaj{" "}
                <select aria-label="Rodzaj nowego zdarzenia" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                  {kinds.map((k) => <option key={k.code} value={k.code}>{k.label}</option>)}
                </select>
              </label>
              <label>Początek <input aria-label="Początek nowego zdarzenia" placeholder="RRRR-MM-DD, RRRR-MM, RRRR albo puste" value={form.event_date} onChange={(e) => setForm({ ...form, event_date: e.target.value })} /></label>
              <label>Koniec <input aria-label="Koniec nowego zdarzenia" placeholder="puste = brak" value={form.event_date_end} disabled={form.is_ongoing} onChange={(e) => setForm({ ...form, event_date_end: e.target.value })} /></label>
              <label><input type="checkbox" aria-label="Nowe zdarzenie trwa nadal" checked={form.is_ongoing} onChange={(e) => setForm({ ...form, is_ongoing: e.target.checked, event_date_end: "" })} /> trwa nadal</label>
              <label>Inne nazwy (po przecinku) <input aria-label="Inne nazwy nowego zdarzenia" value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} style={{ width: "100%" }} /></label>
              <label>Opis <textarea aria-label="Opis nowego zdarzenia" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={{ width: "100%" }} /></label>
              <div><button type="submit" className="button">Dodaj</button> <span style={{ color: "#64748b", fontSize: "0.85em" }}>Uczestników (kraje, organizacje, osoby) dodasz na karcie zdarzenia.</span></div>
            </form>
          </details>
          {!loading && !error && events.length === 0 && <p style={{ color: "#667" }}>Brak zdarzeń.</p>}
          <ul aria-label="Zdarzenia" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {events.map((event) => (
              <WorldEventCard key={event.id} event={event} kinds={kinds} roles={roles} countries={countries}
                apiUrl={apiUrl} headers={headers} onChanged={refresh} onMessage={message} />
            ))}
          </ul>
        </>
      )}

      {tab === "unlinked" && (
        <>
          <p style={{ color: "#667" }}>
            Nazwy wydarzeń zaznaczone w tekstach (prawy klawisz na stronie NER), które nie są jeszcze powiązane z żadnym zdarzeniem rejestru.
          </p>
          {!loading && !error && mentions.length === 0 && <p style={{ color: "#667" }}>Wszystkie nazwy są powiązane.</p>}
          <ul aria-label="Nazwy do powiązania" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {mentions.map((m) => <MentionItem key={m.name_key} mention={m} kinds={kinds} onDecide={decide} />)}
          </ul>
        </>
      )}

      <Pagination page={page} pageSize={pageSize} total={total} isLoading={loading} label="zdarzeń"
        onPageChange={(next) => update({ page: next > 1 ? String(next) : null })} />
    </div>
  );
};

const MentionItem = ({ mention, kinds, onDecide }: {
  mention: MentionGroup; kinds: Kind[];
  onDecide: (path: string, body: Record<string, unknown>, success: string) => Promise<void>;
}) => {
  const [kind, setKind] = React.useState("other");
  const [eventId, setEventId] = React.useState("");
  return (
    <li style={{ padding: "8px 10px", marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
      <strong>📅 {mention.name}</strong>{" "}
      <span style={{ color: "#64748b", fontSize: "0.85em" }}>{mention.document_count} dok. · {mention.mentions} wzmianek</span>
      {mention.description && <div style={{ margin: "4px 0" }}>{mention.description}</div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, fontSize: "0.85em", margin: "4px 0" }}>
        {mention.documents.map((d) => (
          <Link key={d.entity_id} to={`/ner/${d.id}`}>{d.title || `Dokument ${d.id}`} ×{d.mentions}</Link>
        ))}
      </div>

      {mention.suggestions.length > 0 && (
        <div aria-label="Podpowiedzi" style={{ margin: "6px 0" }}>
          {mention.suggestions.map((s) => (
            <div key={s.event.id} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 4 }}>
              <span>
                Czy to <strong>{s.event.title}</strong>{s.event.event_date ? ` (${s.event.event_date})` : " (bez daty)"}?{" "}
                <span style={{ color: "#64748b", fontSize: "0.85em" }}>{s.reason === "alias" ? "ta sama nazwa" : `podobna nazwa ${Math.round(s.score * 100)}%`}</span>
              </span>
              <button type="button" className="button"
                onClick={() => onDecide("mentions/link", { name: mention.name, event_id: s.event.id }, `Powiązano „${mention.name}” ze zdarzeniem „${s.event.title}”.`)}>
                Tak, powiąż
              </button>
              <button type="button" className="button"
                onClick={() => onDecide("mentions/reject", { name: mention.name, event_id: s.event.id }, "Zapamiętano: to nie to zdarzenie.")}>
                To nie to
              </button>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 6 }}>
        <select aria-label={`Rodzaj dla ${mention.name}`} value={kind} onChange={(e) => setKind(e.target.value)}>
          {kinds.map((k) => <option key={k.code} value={k.code}>{k.label}</option>)}
        </select>
        <button type="button" className="button"
          onClick={() => onDecide("from_mention", { name: mention.name, kind }, `Utworzono zdarzenie „${mention.name}” i powiązano je z tekstami.`)}>
          Utwórz zdarzenie
        </button>
        <span style={{ color: "#94a3b8" }}>albo</span>
        <input aria-label={`Numer zdarzenia dla ${mention.name}`} inputMode="numeric" size={6} placeholder="nr zdarzenia" value={eventId}
          onChange={(e) => setEventId(e.target.value)} />
        <button type="button" className="button" disabled={!/^\d+$/.test(eventId)}
          onClick={() => onDecide("mentions/link", { name: mention.name, event_id: Number(eventId) }, `Powiązano „${mention.name}” ze zdarzeniem #${eventId}.`)}>
          Powiąż z istniejącym
        </button>
      </div>
    </li>
  );
};

export default WorldEvents;
