import React from "react";
import axios from "axios";
import { type ApiProps, type Endpoint, type Vocabulary, errorText } from "./types";

export default function ManualRelation({ apiUrl, apiKey, entity, onAdded, disabled }: ApiProps & { entity: Endpoint; onAdded: () => void; disabled: boolean }) {
  const headers = React.useMemo(() => ({ "x-api-key": apiKey }), [apiKey]);
  const [vocabulary, setVocabulary] = React.useState<Vocabulary[]>([]);
  const [incoming, setIncoming] = React.useState(false);
  const [choice, setChoice] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [options, setOptions] = React.useState<Endpoint[]>([]);
  const [selected, setSelected] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [searching, setSearching] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  React.useEffect(() => {
    let active = true;
    axios.get(`${apiUrl}/entity_relations/vocabulary`, { headers }).then(r => { if (active) setVocabulary(r.data.vocabulary ?? []); }).catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, [apiUrl, headers]);
  const choices = vocabulary.flatMap(v => v.pairs.filter(p => (incoming ? p.object : p.subject) === entity.type).map(p => ({
    key: `${v.value}:${incoming ? p.subject : p.object}`, value: v.value, type: incoming ? p.subject : p.object,
    label: `${incoming ? v.inverse_label : v.label} (${({ person: "osoba", organization: "organizacja", country: "państwo" })[incoming ? p.subject : p.object]})`,
  })));
  const current = choices.find(c => c.key === choice);
  const type = current?.type;
  React.useEffect(() => {
    let active = true;
    setOptions([]); setSelected(""); setSearching(false);
    if (!type || (type !== "country" && !query.trim())) return;
    setSearching(true);
    const timer = setTimeout(() => {
      const path = type === "country" ? "countries" : type === "person" ? "persons" : "organizations";
      axios.get(`${apiUrl}/${path}`, { headers, params: type === "country" ? undefined : { q: query.trim(), limit: 20, offset: 0 } }).then(r => {
        // GET /organizations answers with `entries`; the other two lists are named after their path.
        if (active) setOptions((r.data[path === "organizations" ? "entries" : path] ?? []).map((item: { id: number; slug: string; name_pl: string; canonical_name: string }) => type === "country"
          ? { type, slug: item.slug, name: item.name_pl } : { type, id: item.id, name: item.canonical_name }));
      }).catch(e => { if (active) setError(errorText(e)); }).finally(() => { if (active) setSearching(false); });
    }, type === "country" ? 0 : 250);
    return () => { active = false; clearTimeout(timer); };
  }, [apiUrl, headers, type, query]);
  return <details><summary>Dodaj powiązanie ręcznie</summary>
    <form onSubmit={async event => {
      event.preventDefault();
      const other = options.find(o => String(o.id ?? o.slug) === selected);
      if (!other || !current || busy) return;
      const clean = (e: Endpoint) => e.type === "country" ? { type: e.type, slug: e.slug } : { type: e.type, id: e.id };
      setBusy(true); setError("");
      try {
        await axios.post(`${apiUrl}/entity_relations`, { subject: clean(incoming ? other : entity), object: clean(incoming ? entity : other), relation: current.value,
          title: title.trim() || null, valid_from: from || null, valid_to: to || null }, { headers });
        setSelected(""); setTitle(""); setFrom(""); setTo(""); onAdded();
      } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
    }}>
      <fieldset disabled={disabled || busy} style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <label>Kierunek <select value={incoming ? "in" : "out"} onChange={e => { setIncoming(e.target.value === "in"); setChoice(""); setSelected(""); }}><option value="out">Wychodzące</option><option value="in">Przychodzące</option></select></label>
        <label>Relacja <select value={choice} onChange={e => { setChoice(e.target.value); setSelected(""); }}><option value="">Wybierz relację</option>{choices.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}</select></label>
        {type && type !== "country" && <label>Szukaj w rejestrze <input value={query} onChange={e => { setQuery(e.target.value); setSelected(""); }} /></label>}
        <label>Drugi podmiot <select value={selected} onChange={e => setSelected(e.target.value)}><option value="">Wybierz z rejestru</option>{options.map(o => <option key={o.id ?? o.slug} value={o.id ?? o.slug}>{o.name}</option>)}</select></label>
        {searching ? <span role="status">Szukam…</span> : type && (query || type === "country") && options.length === 0 && <span>Brak wyników.</span>}
        <label>Tytuł <input maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label>
        <label>Od <input type="date" value={from} onChange={e => setFrom(e.target.value)} /></label>
        <label>Do <input type="date" min={from || undefined} value={to} onChange={e => setTo(e.target.value)} /></label>
        <button disabled={!selected || !current}>Dodaj powiązanie</button>
      </fieldset>
    </form>{error && <p role="alert">{error}</p>}
  </details>;
}
