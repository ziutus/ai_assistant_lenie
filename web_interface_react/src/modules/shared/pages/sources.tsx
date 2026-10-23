import React from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import type { Source } from "../../../types";

// Source management (table `discovery_sources`, GET/POST/PATCH/DELETE /sources).
// A source is where the user's knowledge comes from: how a document was found ("own", "unknow.news",
// a friend) and, since the knowledge-source fields, what kind of place it is (a course, a newsletter, a
// channel...), how far the user got with it and what they think of it — so a course can be judged by the
// tools and documents it brought. Documents reference the row by id (discovery_source_id, stage 11d),
// so renaming only edits the lookup row and every document follows; sources in use cannot be deleted,
// only deactivated (they disappear from pickers, history stays intact).

const kinds: Array<[string, string]> = [
  ["course", "kurs"], ["training", "szkolenie"], ["newsletter", "newsletter"], ["channel", "kanał"],
  ["book", "książka"], ["person", "osoba"], ["community", "społeczność"], ["website", "strona"], ["other", "inne"],
];
const statuses: Array<[string, string]> = [
  ["planned", "planuję"], ["in_progress", "w trakcie"], ["finished", "ukończone"], ["dropped", "porzucone"],
];
const label = (list: Array<[string, string]>, value?: string | null) => list.find(([key]) => key === value)?.[1] ?? value;

type Form = {
  name: string; description: string; url: string; kind: string; status: string; started_on: string;
  finished_on: string; rating: string; review_note: string; obsidian_note_path: string;
};
const emptyForm: Form = {
  name: "", description: "", url: "", kind: "", status: "", started_on: "", finished_on: "", rating: "",
  review_note: "", obsidian_note_path: "",
};
const formFromSource = (source: Source): Form => ({
  name: source.name, description: source.description ?? "", url: source.url ?? "", kind: source.kind ?? "",
  status: source.status ?? "", started_on: source.started_on ?? "", finished_on: source.finished_on ?? "",
  rating: source.rating ? String(source.rating) : "", review_note: source.review_note ?? "",
  obsidian_note_path: source.obsidian_note_path ?? "",
});
// Empty strings clear a field on the server; the rating is a number or null.
const payload = (form: Form) => ({ ...form, rating: form.rating ? Number(form.rating) : null });

const Sources = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [sources, setSources] = React.useState<Source[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [busyId, setBusyId] = React.useState<number | null>(null);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const [addForm, setAddForm] = React.useState<Form>(emptyForm);
  const [editId, setEditId] = React.useState<number | null>(null);
  const [editForm, setEditForm] = React.useState<Form>(emptyForm);
  const [kindFilter, setKindFilter] = React.useState("");

  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  const report = (text: string, error = false) => {
    setIsError(error);
    setMessage(text);
  };

  const fetchSources = async () => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/sources`, { headers });
      setSources(response.data.sources ?? []);
    } catch (error: any) {
      console.error("Error fetching sources", error);
      report(`Nie udało się pobrać źródeł: ${error.response?.data?.message || error.message}`, true);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const add = async () => {
    if (!addForm.name.trim()) {
      report("Nazwa źródła jest wymagana.", true);
      return;
    }
    setIsError(false);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/sources`, payload(addForm), { headers });
      setAddForm(emptyForm);
      report(`Dodano źródło „${addForm.name.trim()}”.`);
      fetchSources();
    } catch (error: any) {
      console.error("Error adding source", error);
      report(`Nie udało się dodać źródła: ${error.response?.data?.message || error.message}`, true);
    }
  };

  const startEdit = (source: Source) => {
    setEditId(source.id);
    setEditForm(formFromSource(source));
  };

  const saveEdit = async (source: Source) => {
    if (!editForm.name.trim()) {
      report("Nazwa źródła nie może być pusta.", true);
      return;
    }
    setBusyId(source.id);
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/sources/${source.id}`, payload(editForm), { headers });
      const renamed = editForm.name.trim() !== source.name;
      report(renamed
        ? `Zapisano. Zmiana nazwy objęła ${source.count} dokumentów.`
        : "Zapisano zmiany.");
      setEditId(null);
      fetchSources();
    } catch (error: any) {
      console.error("Error updating source", error);
      report(`Nie udało się zapisać: ${error.response?.data?.message || error.message}`, true);
    }
    setBusyId(null);
  };

  const toggleActive = async (source: Source) => {
    setBusyId(source.id);
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/sources/${source.id}`, { is_active: !source.is_active }, { headers });
      report(`Źródło „${source.name}” ${source.is_active ? "dezaktywowane" : "aktywowane"}.`);
      fetchSources();
    } catch (error: any) {
      console.error("Error toggling source", error);
      report(`Nie udało się zmienić aktywności: ${error.response?.data?.message || error.message}`, true);
    }
    setBusyId(null);
  };

  const remove = async (source: Source) => {
    if (!window.confirm(`Usunąć źródło „${source.name}”?`)) {
      return;
    }
    setBusyId(source.id);
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/sources/${source.id}`, { headers });
      report(`Usunięto źródło „${source.name}”.`);
      fetchSources();
    } catch (error: any) {
      console.error("Error deleting source", error);
      report(`Nie udało się usunąć: ${error.response?.data?.message || error.message}`, true);
    }
    setBusyId(null);
  };

  const inputStyle: React.CSSProperties = { padding: "4px 8px", minWidth: 180 };
  const smallLabel: React.CSSProperties = { display: "flex", flexDirection: "column", fontSize: ".8rem", color: "#667" };

  const formFields = (form: Form, set: (value: Form) => void, disabled = false) => (
    <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
      <label style={smallLabel}>Nazwa
        <input type="text" value={form.name} disabled={disabled} style={inputStyle}
          onChange={(e) => set({ ...form, name: e.target.value })} />
      </label>
      <label style={smallLabel}>Rodzaj
        <select value={form.kind} disabled={disabled} style={inputStyle} onChange={(e) => set({ ...form, kind: e.target.value })}>
          <option value="">—</option>
          {kinds.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        </select>
      </label>
      <label style={smallLabel}>Postęp
        <select value={form.status} disabled={disabled} style={inputStyle} onChange={(e) => set({ ...form, status: e.target.value })}>
          <option value="">—</option>
          {statuses.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        </select>
      </label>
      <label style={smallLabel}>Ocena (1–5)
        <select value={form.rating} disabled={disabled} style={{ ...inputStyle, minWidth: 80 }}
          onChange={(e) => set({ ...form, rating: e.target.value })}>
          <option value="">—</option>
          {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
      </label>
      <label style={smallLabel}>Start
        <input type="date" value={form.started_on} disabled={disabled} onChange={(e) => set({ ...form, started_on: e.target.value })} />
      </label>
      <label style={smallLabel}>Koniec
        <input type="date" value={form.finished_on} disabled={disabled} onChange={(e) => set({ ...form, finished_on: e.target.value })} />
      </label>
      <label style={smallLabel}>URL
        <input type="text" value={form.url} disabled={disabled} style={inputStyle} onChange={(e) => set({ ...form, url: e.target.value })} />
      </label>
      <label style={smallLabel}>Opis
        <input type="text" value={form.description} disabled={disabled} style={inputStyle}
          onChange={(e) => set({ ...form, description: e.target.value })} />
      </label>
      <label style={smallLabel}>Notatka w Obsidianie (ścieżka)
        <input type="text" value={form.obsidian_note_path} disabled={disabled} style={inputStyle}
          onChange={(e) => set({ ...form, obsidian_note_path: e.target.value })} />
      </label>
      <label style={{ ...smallLabel, flexBasis: "100%" }}>Czy warto? (Twoja ocena źródła)
        <textarea rows={2} value={form.review_note} disabled={disabled}
          onChange={(e) => set({ ...form, review_note: e.target.value })} />
      </label>
    </div>
  );

  const shown = kindFilter ? sources.filter((source) => (kindFilter === "none" ? !source.kind : source.kind === kindFilter)) : sources;

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Źródła</h2>
      <p style={{ color: "#667", marginBottom: 12 }}>
        Skąd wiem — kanał polecenia dokumentu („own”, newsletter, znajomy) albo kurs, szkolenie, kanał,
        z którego poznałem narzędzia. Ocena i postęp pozwalają ocenić, czy źródło jest warte czasu.
        Zmiana nazwy aktualizuje wszystkie dokumenty; źródła użyte w dokumentach można tylko dezaktywować.
      </p>

      <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 10, marginBottom: 8 }}>
        {formFields(addForm, setAddForm)}
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className={"button"} type="button" disabled={isLoading} onClick={add}>
            + Dodaj źródło
          </button>
          <button className={"button"} type="button" disabled={isLoading} onClick={fetchSources}>
            Odśwież
          </button>
          <label style={{ marginLeft: "auto", display: "inline-flex", gap: 6, alignItems: "center" }}>
            Rodzaj:
            <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
              <option value="">wszystkie</option>
              {kinds.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
              <option value="none">bez rodzaju</option>
            </select>
          </label>
        </div>
      </div>

      {isLoading && <div className={"loader"}></div>}
      {message && (
        <p className={isError ? "errorText" : undefined} style={isError ? undefined : { color: "#2e7d43" }}>
          {message}
        </p>
      )}

      <ul style={{ listStyle: "none", padding: 0, marginTop: 14 }}>
        {shown.map((source) => (
          <li
            key={source.id}
            style={{
              padding: "10px 8px",
              borderBottom: "1px solid #eee",
              opacity: busyId === source.id ? 0.5 : source.is_active ? 1 : 0.65,
            }}
          >
            {editId === source.id ? (
              <div>
                {formFields(editForm, setEditForm, busyId === source.id)}
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
                  <button className={"button"} type="button" disabled={busyId === source.id} onClick={() => saveEdit(source)}>
                    Zapisz
                  </button>
                  <button className={"button"} type="button" onClick={() => setEditId(null)}>
                    Anuluj
                  </button>
                  {editForm.name.trim() !== source.name && source.count > 0 && (
                    <span style={{ color: "#a66", fontSize: "0.9em" }}>
                      Zmiana nazwy zaktualizuje {source.count} dokumentów.
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <strong>{source.name}</strong>
                  {source.kind && (
                    <span style={{ background: "#e2e8f0", color: "#334155", borderRadius: 4, padding: "1px 6px", fontSize: "0.8em" }}>
                      {label(kinds, source.kind)}
                    </span>
                  )}
                  {source.status && <span style={{ color: "#475569", fontSize: "0.85em" }}>{label(statuses, source.status)}</span>}
                  {source.rating ? <span title={`Ocena ${source.rating} z 5`} style={{ color: "#b45309" }}>{"★".repeat(source.rating)}{"☆".repeat(5 - source.rating)}</span> : null}
                  <span style={{ color: "#667" }} title="Dokumenty z tego źródła">×{source.count}</span>
                  {!source.is_active && (
                    <span style={{ background: "#eee", borderRadius: 4, padding: "1px 6px", fontSize: "0.85em" }}>
                      nieaktywne
                    </span>
                  )}
                  {source.description && <span style={{ color: "#667" }}>{source.description}</span>}
                  {source.url && (
                    <a href={source.url} target="_blank" rel="noopener noreferrer" style={{ color: "#0369a1" }}>
                      {source.url}
                    </a>
                  )}
                  <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                    <button className={"button"} type="button" disabled={busyId === source.id} onClick={() => startEdit(source)}>
                      Edytuj
                    </button>
                    <button className={"button"} type="button" disabled={busyId === source.id} onClick={() => toggleActive(source)}>
                      {source.is_active ? "Dezaktywuj" : "Aktywuj"}
                    </button>
                    {source.count === 0 && !source.tools?.length && (
                      <button className={"button"} type="button" disabled={busyId === source.id} onClick={() => remove(source)}>
                        Usuń
                      </button>
                    )}
                  </span>
                </div>
                {(source.started_on || source.finished_on) && (
                  <div style={{ color: "#64748b", fontSize: ".85rem" }}>
                    {source.started_on ?? "?"} → {source.finished_on ?? "…"}
                  </div>
                )}
                {source.review_note && <blockquote style={{ margin: "6px 0", color: "#475569", borderLeft: "3px solid #cbd5e1", paddingLeft: 10, whiteSpace: "pre-wrap" }}>{source.review_note}</blockquote>}
                {source.obsidian_note_path && <div style={{ color: "#64748b", fontSize: ".85rem" }}>Notatka: {source.obsidian_note_path}</div>}
                {source.tools && source.tools.length > 0 && (
                  <div style={{ fontSize: ".85rem", marginTop: 4 }}>
                    Narzędzia z tego źródła ({source.tools.length}):{" "}
                    {source.tools.map((tool, index) => (
                      <span key={tool.id}>{index > 0 && ", "}<Link to={`/tools?tool=${tool.id}`}>{tool.name}</Link></span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>

      {!isLoading && !shown.length && (
        <p style={{ color: "#667" }}>{sources.length ? "Brak źródeł tego rodzaju." : "Brak źródeł — dodaj pierwsze powyżej."}</p>
      )}
    </div>
  );
};

export default Sources;
