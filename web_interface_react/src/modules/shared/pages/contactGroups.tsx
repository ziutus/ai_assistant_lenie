import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";

// Contact group lookup (table `contact_groups`, GET/POST/PATCH/DELETE
// /contact_groups) — many-to-many, distinct from contactCategories.tsx's
// single-value category. Mirrors that page's layout.

export interface ContactGroup {
  id: number;
  name: string;
  description: string | null;
  count: number;
}

const emptyForm = { name: "", description: "" };

const ContactGroups = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [groups, setGroups] = React.useState<ContactGroup[]>([]);
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

  const fetchGroups = async () => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/contact_groups`, { headers });
      setGroups(response.data.contact_groups ?? []);
    } catch (error: any) {
      console.error("Error fetching contact groups", error);
      report(`Nie udało się pobrać grup: ${error.response?.data?.message || error.message}`, true);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchGroups();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const add = async () => {
    if (!addForm.name.trim()) {
      report("Nazwa grupy jest wymagana.", true);
      return;
    }
    setIsError(false);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/contact_groups`, addForm, { headers });
      setAddForm(emptyForm);
      report(`Dodano grupę „${addForm.name.trim()}”.`);
      fetchGroups();
    } catch (error: any) {
      console.error("Error adding contact group", error);
      report(`Nie udało się dodać grupy: ${error.response?.data?.message || error.message}`, true);
    }
  };

  const startEdit = (group: ContactGroup) => {
    setEditId(group.id);
    setEditForm({ name: group.name, description: group.description ?? "" });
  };

  const saveEdit = async (group: ContactGroup) => {
    if (!editForm.name.trim()) {
      report("Nazwa grupy nie może być pusta.", true);
      return;
    }
    setBusyId(group.id);
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/contact_groups/${group.id}`, editForm, { headers });
      report("Zapisano zmiany.");
      setEditId(null);
      fetchGroups();
    } catch (error: any) {
      console.error("Error updating contact group", error);
      report(`Nie udało się zapisać: ${error.response?.data?.message || error.message}`, true);
    }
    setBusyId(null);
  };

  const remove = async (group: ContactGroup) => {
    if (!window.confirm(`Usunąć grupę „${group.name}”?`)) {
      return;
    }
    setBusyId(group.id);
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/contact_groups/${group.id}`, { headers });
      report(`Usunięto grupę „${group.name}”.`);
      fetchGroups();
    } catch (error: any) {
      console.error("Error deleting contact group", error);
      report(`Nie udało się usunąć: ${error.response?.data?.message || error.message}`, true);
    }
    setBusyId(null);
  };

  const inputStyle: React.CSSProperties = { padding: "4px 8px", minWidth: 180 };

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Grupy kontaktów</h2>
      <p style={{ color: "#667", marginBottom: 12 }}>
        Grupy przypisywane do prywatnych kontaktów (np. „Tuwima Gardens Mieszkańcy”, „Rodzina”) — w
        odróżnieniu od kategorii, jeden kontakt może należeć do wielu grup naraz. Grupy użyte przez
        kontakty można usunąć dopiero po odpięciu ich od wszystkich kontaktów.
      </p>

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <input
          type="text"
          placeholder="Nazwa nowej grupy"
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
        <button className={"button"} type="button" disabled={isLoading} onClick={add}>
          + Dodaj grupę
        </button>
        <button className={"button"} type="button" disabled={isLoading} onClick={fetchGroups}>
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
        {groups.map((group) => (
          <li
            key={group.id}
            style={{ padding: "10px 8px", borderBottom: "1px solid #eee", opacity: busyId === group.id ? 0.5 : 1 }}
          >
            {editId === group.id ? (
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
                <button className={"button"} type="button" disabled={busyId === group.id} onClick={() => saveEdit(group)}>
                  Zapisz
                </button>
                <button className={"button"} type="button" onClick={() => setEditId(null)}>
                  Anuluj
                </button>
              </div>
            ) : (
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <strong>{group.name}</strong>
                <span style={{ color: "#667" }}>×{group.count}</span>
                {group.description && <span style={{ color: "#667" }}>{group.description}</span>}
                <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                  <button className={"button"} type="button" disabled={busyId === group.id} onClick={() => startEdit(group)}>
                    Edytuj
                  </button>
                  {group.count === 0 && (
                    <button className={"button"} type="button" disabled={busyId === group.id} onClick={() => remove(group)}>
                      Usuń
                    </button>
                  )}
                </span>
              </div>
            )}
          </li>
        ))}
      </ul>

      {!isLoading && !groups.length && (
        <p style={{ color: "#667" }}>Brak grup — dodaj pierwszą powyżej.</p>
      )}
    </div>
  );
};

export default ContactGroups;
