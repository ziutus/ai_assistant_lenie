import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";
import type { Source } from "../../../types";

// Discovery-source management (table `discovery_sources`, GET/POST/PATCH/DELETE /sources).
// source = how the user found a document ("own", "unknow.news", a friend) — a
// recommendation channel, not the author. Documents reference the row by id
// (discovery_source_id, stage 11d), so renaming only edits the lookup row and
// every document follows; sources in use cannot be deleted, only deactivated
// (they disappear from pickers, history stays intact).

const emptyForm = { name: "", description: "", url: "" };

const Sources = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [sources, setSources] = React.useState<Source[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [busyId, setBusyId] = React.useState<number | null>(null);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const [addForm, setAddForm] = React.useState(emptyForm);
  const [editId, setEditId] = React.useState<number | null>(null);
  const [editForm, setEditForm] = React.useState(emptyForm);

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
      await axios.post(`${apiUrl}/sources`, addForm, { headers });
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
    setEditForm({
      name: source.name,
      description: source.description ?? "",
      url: source.url ?? "",
    });
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
      await axios.patch(`${apiUrl}/sources/${source.id}`, editForm, { headers });
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

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Źródła</h2>
      <p style={{ color: "#667", marginBottom: 12 }}>
        Skąd znam dokument (kanał polecenia — „own”, newsletter, znajomy). Zmiana nazwy
        aktualizuje wszystkie dokumenty; źródła użyte w dokumentach można tylko dezaktywować.
      </p>

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <input
          type="text"
          placeholder="Nazwa nowego źródła"
          value={addForm.name}
          onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
          style={inputStyle}
        />
        <input
          type="text"
          placeholder="Opis (opcjonalnie)"
          value={addForm.description}
          onChange={(e) => setAddForm({ ...addForm, description: e.target.value })}
          style={inputStyle}
        />
        <input
          type="text"
          placeholder="URL (opcjonalnie)"
          value={addForm.url}
          onChange={(e) => setAddForm({ ...addForm, url: e.target.value })}
          style={inputStyle}
        />
        <button className={"button"} type="button" disabled={isLoading} onClick={add}>
          + Dodaj źródło
        </button>
        <button className={"button"} type="button" disabled={isLoading} onClick={fetchSources}>
          Odśwież
        </button>
      </div>

      {isLoading && <div className={"loader"}></div>}
      {message && (
        <p className={isError ? "errorText" : undefined} style={isError ? undefined : { color: "#2e7d43" }}>
          {message}
        </p>
      )}

      <ul style={{ listStyle: "none", padding: 0, marginTop: 14 }}>
        {sources.map((source) => (
          <li
            key={source.id}
            style={{
              padding: "10px 8px",
              borderBottom: "1px solid #eee",
              opacity: busyId === source.id ? 0.5 : source.is_active ? 1 : 0.65,
            }}
          >
            {editId === source.id ? (
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <input
                  type="text"
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  style={inputStyle}
                />
                <input
                  type="text"
                  placeholder="Opis"
                  value={editForm.description}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  style={inputStyle}
                />
                <input
                  type="text"
                  placeholder="URL"
                  value={editForm.url}
                  onChange={(e) => setEditForm({ ...editForm, url: e.target.value })}
                  style={inputStyle}
                />
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
            ) : (
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <strong>{source.name}</strong>
                <span style={{ color: "#667" }}>×{source.count}</span>
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
                  {source.count === 0 && (
                    <button className={"button"} type="button" disabled={busyId === source.id} onClick={() => remove(source)}>
                      Usuń
                    </button>
                  )}
                </span>
              </div>
            )}
          </li>
        ))}
      </ul>

      {!isLoading && !sources.length && (
        <p style={{ color: "#667" }}>Brak źródeł — dodaj pierwsze powyżej.</p>
      )}
    </div>
  );
};

export default Sources;
