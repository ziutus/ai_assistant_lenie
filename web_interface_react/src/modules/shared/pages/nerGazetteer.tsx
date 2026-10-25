import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// Database additions to the curated NER gazetteers (ADR-029): GET/POST/PATCH/DELETE /ner_gazetteer.
// The lists in code stay the seed; rows added here take effect within the backend's 60 s cache.
// Writes need a `service` API key, so a 403 is explained instead of shown raw.

type Kind = "city" | "geocode_alias" | "place_mention";
type Entry = {
  id: number; kind: Kind; name_pl: string; patterns: string[]; geocode_alias: string | null;
  note: string | null; source_document_id: number | null; created_by: string | null; created_at: string | null;
};

const KIND_LABEL: Record<Kind, string> = {
  city: "Miasto / stan (wzorce)", geocode_alias: "Alias geokodera", place_mention: "Miejsce wykrywane w tekście (wzorce)",
};
const hasPatterns = (kind: Kind) => kind !== "geocode_alias";
const day = (value: string | null) => (value ? value.replace("T", " ").slice(0, 16) : "—");
const parsePatterns = (text: string) => text.split(/[\n,]+/).map(p => p.trim()).filter(Boolean);

const errorText = (e: unknown, fallback: string) => {
  const err = e as { response?: { status?: number; data?: { message?: string } } };
  if (err.response?.status === 403) return "Zapis wymaga klucza API typu service.";
  return err.response?.data?.message ?? fallback;
};

const NerGazetteer = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const kindFilter = searchParams.get("kind") ?? "";
  const [entries, setEntries] = React.useState<Entry[] | null>(null);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [confirmDelete, setConfirmDelete] = React.useState<number | null>(null);
  const [editId, setEditId] = React.useState<number | null>(null);
  const [edit, setEdit] = React.useState({ patterns: "", geocode_alias: "", note: "" });
  const [form, setForm] = React.useState({ kind: "city" as Kind, name_pl: "", patterns: "", geocode_alias: "", note: "", source: "" });

  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "", "Content-Type": "application/json" }), [apiKey]);

  const load = React.useCallback(() => {
    axios.get(`${apiUrl}/ner_gazetteer`, { headers, params: kindFilter ? { kind: kindFilter } : {} })
      .then(response => { setEntries(response.data.entries); setError(""); })
      .catch(e => setError(errorText(e, "Nie udało się pobrać wpisów gazetteera")));
  }, [apiUrl, headers, kindFilter]);

  React.useEffect(load, [load]);

  const add = (event: React.FormEvent) => {
    event.preventDefault();
    setNotice(""); setError("");
    const source = form.source.trim();
    const body: Record<string, unknown> = { kind: form.kind, name_pl: form.name_pl, note: form.note.trim() || null };
    if (hasPatterns(form.kind)) body.patterns = parsePatterns(form.patterns);
    else body.geocode_alias = form.geocode_alias;
    if (source) body.source_document_id = Number(source);
    axios.post(`${apiUrl}/ner_gazetteer`, body, { headers })
      .then(() => {
        setNotice(`Dodano „${form.name_pl.trim()}”. Zadziała przy kolejnym przebiegu NER (cache do 60 s).`);
        setForm({ ...form, name_pl: "", patterns: "", geocode_alias: "", note: "", source: "" });
        load();
      })
      .catch(e => setError(errorText(e, "Nie udało się dodać wpisu")));
  };

  const startEdit = (entry: Entry) => {
    setEditId(entry.id);
    setEdit({ patterns: entry.patterns.join("\n"), geocode_alias: entry.geocode_alias ?? "", note: entry.note ?? "" });
  };

  const saveEdit = (entry: Entry) => {
    setNotice(""); setError("");
    const body: Record<string, unknown> = { note: edit.note.trim() || null };
    if (hasPatterns(entry.kind)) body.patterns = parsePatterns(edit.patterns);
    else body.geocode_alias = edit.geocode_alias;
    axios.patch(`${apiUrl}/ner_gazetteer/${entry.id}`, body, { headers })
      .then(() => { setEditId(null); setNotice(`Zapisano „${entry.name_pl}”.`); load(); })
      .catch(e => setError(errorText(e, "Nie udało się zapisać zmian")));
  };

  const remove = (entry: Entry) => {
    setNotice(""); setError("");
    axios.delete(`${apiUrl}/ner_gazetteer/${entry.id}`, { headers })
      .then(() => { setConfirmDelete(null); setNotice(`Usunięto „${entry.name_pl}”.`); load(); })
      .catch(e => setError(errorText(e, "Nie udało się usunąć wpisu")));
  };

  const tableStyle: React.CSSProperties = { width: "100%", borderCollapse: "collapse", marginTop: 10 };
  const th: React.CSSProperties = { textAlign: "left", padding: "7px 8px", borderBottom: "1px solid #cbd5e1" };
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid #e2e8f0", verticalAlign: "top" };
  const muted: React.CSSProperties = { color: "#64748b", fontSize: "0.85em" };
  const field: React.CSSProperties = { display: "block", marginBottom: 8 };

  return <div>
    <h2>Gazetteer NER — wpisy w bazie</h2>
    <p style={muted}>
      Dodatki do zamkniętych list NER (<code>city_gazetteer</code>, <code>geocode_aliases</code>, <code>place_mention_gazetteer</code>), bez zmiany kodu i deployu.
      Listy z kodu zostają bazą, wpisy stąd tylko je uzupełniają. Wzorzec: rdzeń z <code>*</code> na końcu członu
      (np. <code>luizjan*</code>), co najmniej 3 znaki przed <code>*</code>, bez polskich znaków i wielkich liter.
    </p>
    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    {notice && <p role="status" style={{ color: "#15803d" }}>{notice}</p>}

    <form onSubmit={add} style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <h3 style={{ marginTop: 0 }}>Dodaj wpis</h3>
      <label style={field}>Rodzaj{" "}
        <select aria-label="Rodzaj wpisu" value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value as Kind })}>
          <option value="city">{KIND_LABEL.city}</option>
          <option value="geocode_alias">{KIND_LABEL.geocode_alias}</option>
          <option value="place_mention">{KIND_LABEL.place_mention}</option>
        </select>
      </label>
      <label style={field}>Nazwa polska{" "}
        <input aria-label="Nazwa polska" value={form.name_pl} onChange={e => setForm({ ...form, name_pl: e.target.value })} required maxLength={200} />
      </label>
      {hasPatterns(form.kind)
        ? <label style={field}>Wzorce (jeden w linii lub po przecinku){" "}
            <textarea aria-label="Wzorce" rows={3} value={form.patterns} onChange={e => setForm({ ...form, patterns: e.target.value })} required />
          </label>
        : <label style={field}>Zapytanie do geokodera{" "}
            <input aria-label="Alias geokodera" value={form.geocode_alias} onChange={e => setForm({ ...form, geocode_alias: e.target.value })} required maxLength={200} />
          </label>}
      <label style={field}>Dokument źródłowy (id, opcjonalnie){" "}
        <input aria-label="Dokument źródłowy" type="number" min={1} value={form.source} onChange={e => setForm({ ...form, source: e.target.value })} />
      </label>
      <label style={field}>Notatka{" "}
        <input aria-label="Notatka" value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} />
      </label>
      <button type="submit">Dodaj</button>
    </form>

    <label>Rodzaj:{" "}
      <select aria-label="Filtr rodzaju" value={kindFilter}
        onChange={e => setSearchParams(e.target.value ? { kind: e.target.value } : {})}>
        <option value="">wszystkie</option>
        <option value="city">{KIND_LABEL.city}</option>
        <option value="geocode_alias">{KIND_LABEL.geocode_alias}</option>
        <option value="place_mention">{KIND_LABEL.place_mention}</option>
      </select>
    </label>
    {!entries && !error && <p>Ładuję…</p>}
    {entries && <>
      <table style={tableStyle}><thead><tr>
        <th style={th}>Nazwa</th><th style={th}>Wzorce / alias</th><th style={th}>Notatka</th><th style={th}>Akcje</th>
      </tr></thead><tbody>
        {entries.map(entry => <tr key={entry.id}>
          <td style={td}>
            <strong>{entry.name_pl}</strong>
            <div style={muted}>
              #{entry.id} · {KIND_LABEL[entry.kind]}
              {entry.source_document_id != null && <> · <NavLink to={`/read/${entry.source_document_id}`}>dok. #{entry.source_document_id}</NavLink></>}
            </div>
          </td>
          <td style={td}>
            {editId === entry.id
              ? (hasPatterns(entry.kind)
                  ? <textarea aria-label={`Wzorce ${entry.name_pl}`} rows={3} value={edit.patterns} onChange={e => setEdit({ ...edit, patterns: e.target.value })} />
                  : <input aria-label={`Alias ${entry.name_pl}`} value={edit.geocode_alias} onChange={e => setEdit({ ...edit, geocode_alias: e.target.value })} />)
              : (hasPatterns(entry.kind) ? entry.patterns.map(p => <code key={p} style={{ marginRight: 8 }}>{p}</code>) : entry.geocode_alias)}
          </td>
          <td style={td}>
            {editId === entry.id
              ? <input aria-label={`Notatka ${entry.name_pl}`} value={edit.note} onChange={e => setEdit({ ...edit, note: e.target.value })} />
              : <>{entry.note ?? "—"}<div style={muted}>{entry.created_by ?? "—"} · {day(entry.created_at)}</div></>}
          </td>
          <td style={td}>
            {editId === entry.id
              ? <><button type="button" onClick={() => saveEdit(entry)}>Zapisz</button>{" "}
                  <button type="button" onClick={() => setEditId(null)}>Anuluj</button></>
              : <><button type="button" onClick={() => startEdit(entry)}>Edytuj</button>{" "}
                  {confirmDelete === entry.id
                    ? <><button type="button" onClick={() => remove(entry)}>Potwierdź usunięcie</button>{" "}
                        <button type="button" onClick={() => setConfirmDelete(null)}>Anuluj</button></>
                    : <button type="button" onClick={() => setConfirmDelete(entry.id)}>Usuń</button>}</>}
          </td>
        </tr>)}
      </tbody></table>
      {!entries.length && <p>Brak wpisów w bazie — działają tylko listy z kodu.</p>}
    </>}
  </div>;
};

export default NerGazetteer;
