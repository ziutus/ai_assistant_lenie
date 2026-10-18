import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

// Per-channel glossary of expected names (GET/POST/PATCH/DELETE /ner_channel_glossary): the backend
// repairs speech-to-text slips ("Hekset", "Hexeta", "He H" -> Hegseth) in a copy of the transcript
// before NER; the stored transcript is never changed. Takes effect on the next entity refresh.

type Entry = {
  id: number; author: string; canonical_name: string; aliases: string[]; fuzzy: boolean;
  note: string | null; created_by: string | null; created_at: string | null;
};

const day = (value: string | null) => (value ? value.replace("T", " ").slice(0, 16) : "—");
const parseAliases = (text: string) => text.split(/\n+/).map(a => a.trim()).filter(Boolean);

const errorText = (e: unknown, fallback: string) => {
  const err = e as { response?: { data?: { message?: string } } };
  return err.response?.data?.message ?? fallback;
};

const NerChannelGlossary = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const authorFilter = searchParams.get("author") ?? "";
  const [entries, setEntries] = React.useState<Entry[] | null>(null);
  const [authors, setAuthors] = React.useState<string[]>([]);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [confirmDelete, setConfirmDelete] = React.useState<number | null>(null);
  const [editId, setEditId] = React.useState<number | null>(null);
  const [edit, setEdit] = React.useState({ aliases: "", fuzzy: true, note: "" });
  const [form, setForm] = React.useState({ author: authorFilter, canonical_name: "", aliases: "", fuzzy: true, note: "" });

  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "", "Content-Type": "application/json" }), [apiKey]);

  const load = React.useCallback(() => {
    axios.get(`${apiUrl}/ner_channel_glossary`, { headers, params: authorFilter ? { author: authorFilter } : {} })
      .then(response => { setEntries(response.data.entries); setAuthors(response.data.authors ?? []); setError(""); })
      .catch(e => setError(errorText(e, "Nie udało się pobrać słownika kanału")));
  }, [apiUrl, headers, authorFilter]);

  React.useEffect(load, [load]);

  const add = (event: React.FormEvent) => {
    event.preventDefault();
    setNotice(""); setError("");
    const body = {
      author: form.author, canonical_name: form.canonical_name, aliases: parseAliases(form.aliases),
      fuzzy: form.fuzzy, note: form.note.trim() || null,
    };
    axios.post(`${apiUrl}/ner_channel_glossary`, body, { headers })
      .then(() => {
        setNotice(`Dodano „${form.canonical_name.trim()}”. Zadziała przy następnym odświeżeniu encji dokumentu.`);
        setForm({ ...form, canonical_name: "", aliases: "", note: "" });
        load();
      })
      .catch(e => setError(errorText(e, "Nie udało się dodać wpisu")));
  };

  const startEdit = (entry: Entry) => {
    setEditId(entry.id);
    setEdit({ aliases: entry.aliases.join("\n"), fuzzy: entry.fuzzy, note: entry.note ?? "" });
  };

  const saveEdit = (entry: Entry) => {
    setNotice(""); setError("");
    axios.patch(`${apiUrl}/ner_channel_glossary/${entry.id}`,
      { aliases: parseAliases(edit.aliases), fuzzy: edit.fuzzy, note: edit.note.trim() || null }, { headers })
      .then(() => { setEditId(null); setNotice(`Zapisano „${entry.canonical_name}”.`); load(); })
      .catch(e => setError(errorText(e, "Nie udało się zapisać zmian")));
  };

  const remove = (entry: Entry) => {
    setNotice(""); setError("");
    axios.delete(`${apiUrl}/ner_channel_glossary/${entry.id}`, { headers })
      .then(() => { setConfirmDelete(null); setNotice(`Usunięto „${entry.canonical_name}”.`); load(); })
      .catch(e => setError(errorText(e, "Nie udało się usunąć wpisu")));
  };

  const tableStyle: React.CSSProperties = { width: "100%", borderCollapse: "collapse", marginTop: 10 };
  const th: React.CSSProperties = { textAlign: "left", padding: "7px 8px", borderBottom: "1px solid #cbd5e1" };
  const td: React.CSSProperties = { padding: "7px 8px", borderBottom: "1px solid #e2e8f0", verticalAlign: "top" };
  const muted: React.CSSProperties = { color: "#64748b", fontSize: "0.85em" };
  const field: React.CSSProperties = { display: "block", marginBottom: 8 };

  return <div>
    <h2>Słownik nazw kanału (poprawki transkrypcji dla NER)</h2>
    <p style={muted}>
      Nazwy oczekiwane na danym kanale (pole <em>byline</em> dokumentu). Przed rozpoznawaniem encji kopia tekstu jest
      poprawiana: <strong>aliasy</strong> (dokładne frazy, np. <code>He H</code>) zamieniane są na pełną nazwę, a przy
      włączonym <strong>dopasowaniu przybliżonym</strong> wyraz zapisany wielką literą, który brzmi jak ostatni człon
      nazwy (np. <code>Hekset</code>, <code>Hexeta</code> → <code>Hegseth</code>), zamieniany jest na ten człon.
      Zapisany transkrypt się nie zmienia. Zmiana działa przy następnym „Wykryj osoby i miejsca”.
    </p>
    {error && <p role="alert" style={{ color: "#b91c1c" }}>{error}</p>}
    {notice && <p role="status" style={{ color: "#15803d" }}>{notice}</p>}

    <form onSubmit={add} style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <h3 style={{ marginTop: 0 }}>Dodaj nazwę</h3>
      <label style={field}>Kanał (byline){" "}
        <input aria-label="Kanał" list="glossary-authors" value={form.author} required maxLength={200}
          onChange={e => setForm({ ...form, author: e.target.value })} />
        <datalist id="glossary-authors">{authors.map(a => <option key={a} value={a} />)}</datalist>
      </label>
      <label style={field}>Poprawna nazwa (np. Pete Hegseth){" "}
        <input aria-label="Poprawna nazwa" value={form.canonical_name} required maxLength={200}
          onChange={e => setForm({ ...form, canonical_name: e.target.value })} />
      </label>
      <label style={field}>Aliasy — błędne frazy, jedna w linii (opcjonalnie){" "}
        <textarea aria-label="Aliasy" rows={3} value={form.aliases}
          onChange={e => setForm({ ...form, aliases: e.target.value })} />
      </label>
      <label style={field}>
        <input type="checkbox" aria-label="Dopasowanie przybliżone" checked={form.fuzzy}
          onChange={e => setForm({ ...form, fuzzy: e.target.checked })} />{" "}
        Dopasowanie przybliżone ostatniego członu nazwy
      </label>
      <label style={field}>Notatka{" "}
        <input aria-label="Notatka" value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} />
      </label>
      <button type="submit">Dodaj</button>
    </form>

    <label>Kanał:{" "}
      <select aria-label="Filtr kanału" value={authorFilter}
        onChange={e => setSearchParams(e.target.value ? { author: e.target.value } : {})}>
        <option value="">wszystkie</option>
        {authors.map(a => <option key={a} value={a}>{a}</option>)}
      </select>
    </label>
    {!entries && !error && <p>Ładuję…</p>}
    {entries && <>
      <table style={tableStyle}><thead><tr>
        <th style={th}>Nazwa</th><th style={th}>Aliasy / tryb</th><th style={th}>Notatka</th><th style={th}>Akcje</th>
      </tr></thead><tbody>
        {entries.map(entry => <tr key={entry.id}>
          <td style={td}>
            <strong>{entry.canonical_name}</strong>
            <div style={muted}>#{entry.id} · {entry.author}</div>
          </td>
          <td style={td}>
            {editId === entry.id
              ? <>
                  <textarea aria-label={`Aliasy ${entry.canonical_name}`} rows={3} value={edit.aliases}
                    onChange={e => setEdit({ ...edit, aliases: e.target.value })} />
                  <label style={{ display: "block" }}>
                    <input type="checkbox" aria-label={`Przybliżone ${entry.canonical_name}`} checked={edit.fuzzy}
                      onChange={e => setEdit({ ...edit, fuzzy: e.target.checked })} /> przybliżone
                  </label>
                </>
              : <>
                  {entry.aliases.map(a => <code key={a} style={{ marginRight: 8 }}>{a}</code>)}
                  <div style={muted}>{entry.fuzzy ? "dopasowanie przybliżone: tak" : "dopasowanie przybliżone: nie"}</div>
                </>}
          </td>
          <td style={td}>
            {editId === entry.id
              ? <input aria-label={`Notatka ${entry.canonical_name}`} value={edit.note}
                  onChange={e => setEdit({ ...edit, note: e.target.value })} />
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
      {!entries.length && <p>Brak wpisów{authorFilter ? " dla tego kanału" : ""}.</p>}
    </>}
    <p style={muted}>Zobacz też: <NavLink to="/ner-gazetteer">Gazetteer NER</NavLink></p>
  </div>;
};

export default NerChannelGlossary;
