import React from "react";
import axios from "axios";
import { AuthorizationContext } from "../context/authorizationContext";

// Contact category lookup (table `contact_categories`, GET/POST/PATCH/DELETE
// /contact_categories) — managed from the UI so new categories don't need a
// migration. Mirrors pages/sources.tsx.

export interface ContactCategory {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  count: number;
}

const emptyForm = { name: "", description: "" };

const ContactCategories = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [categories, setCategories] = React.useState<ContactCategory[]>([]);
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

  const fetchCategories = async () => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.get(`${apiUrl}/contact_categories`, { headers });
      setCategories(response.data.contact_categories ?? []);
    } catch (error: any) {
      console.error("Error fetching contact categories", error);
      report(`Nie udało się pobrać kategorii: ${error.response?.data?.message || error.message}`, true);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchCategories();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const add = async () => {
    if (!addForm.name.trim()) {
      report("Nazwa kategorii jest wymagana.", true);
      return;
    }
    setIsError(false);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/contact_categories`, addForm, { headers });
      setAddForm(emptyForm);
      report(`Dodano kategorię „${addForm.name.trim()}”.`);
      fetchCategories();
    } catch (error: any) {
      console.error("Error adding contact category", error);
      report(`Nie udało się dodać kategorii: ${error.response?.data?.message || error.message}`, true);
    }
  };

  const startEdit = (category: ContactCategory) => {
    setEditId(category.id);
    setEditForm({ name: category.name, description: category.description ?? "" });
  };

  const saveEdit = async (category: ContactCategory) => {
    if (!editForm.name.trim()) {
      report("Nazwa kategorii nie może być pusta.", true);
      return;
    }
    setBusyId(category.id);
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/contact_categories/${category.id}`, editForm, { headers });
      report("Zapisano zmiany.");
      setEditId(null);
      fetchCategories();
    } catch (error: any) {
      console.error("Error updating contact category", error);
      report(`Nie udało się zapisać: ${error.response?.data?.message || error.message}`, true);
    }
    setBusyId(null);
  };

  const toggleActive = async (category: ContactCategory) => {
    setBusyId(category.id);
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/contact_categories/${category.id}`, { is_active: !category.is_active }, { headers });
      report(`Kategoria „${category.name}” ${category.is_active ? "dezaktywowana" : "aktywowana"}.`);
      fetchCategories();
    } catch (error: any) {
      console.error("Error toggling contact category", error);
      report(`Nie udało się zmienić aktywności: ${error.response?.data?.message || error.message}`, true);
    }
    setBusyId(null);
  };

  const remove = async (category: ContactCategory) => {
    if (!window.confirm(`Usunąć kategorię „${category.name}”?`)) {
      return;
    }
    setBusyId(category.id);
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/contact_categories/${category.id}`, { headers });
      report(`Usunięto kategorię „${category.name}”.`);
      fetchCategories();
    } catch (error: any) {
      console.error("Error deleting contact category", error);
      report(`Nie udało się usunąć: ${error.response?.data?.message || error.message}`, true);
    }
    setBusyId(null);
  };

  const inputStyle: React.CSSProperties = { padding: "4px 8px", minWidth: 180 };

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Kategorie kontaktów</h2>
      <p style={{ color: "#667", marginBottom: 12 }}>
        Kategorie przypisywane do prywatnych kontaktów (np. „Osoba prywatna”). Kategorie użyte przez
        kontakty można tylko dezaktywować, nie usunąć.
      </p>

      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <input
          type="text"
          placeholder="Nazwa nowej kategorii"
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
          + Dodaj kategorię
        </button>
        <button className={"button"} type="button" disabled={isLoading} onClick={fetchCategories}>
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
        {categories.map((category) => (
          <li
            key={category.id}
            style={{
              padding: "10px 8px",
              borderBottom: "1px solid #eee",
              opacity: busyId === category.id ? 0.5 : category.is_active ? 1 : 0.65,
            }}
          >
            {editId === category.id ? (
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
                <button className={"button"} type="button" disabled={busyId === category.id} onClick={() => saveEdit(category)}>
                  Zapisz
                </button>
                <button className={"button"} type="button" onClick={() => setEditId(null)}>
                  Anuluj
                </button>
              </div>
            ) : (
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <strong>{category.name}</strong>
                <span style={{ color: "#667" }}>×{category.count}</span>
                {!category.is_active && (
                  <span style={{ background: "#eee", borderRadius: 4, padding: "1px 6px", fontSize: "0.85em" }}>
                    nieaktywne
                  </span>
                )}
                {category.description && <span style={{ color: "#667" }}>{category.description}</span>}
                <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                  <button className={"button"} type="button" disabled={busyId === category.id} onClick={() => startEdit(category)}>
                    Edytuj
                  </button>
                  <button className={"button"} type="button" disabled={busyId === category.id} onClick={() => toggleActive(category)}>
                    {category.is_active ? "Dezaktywuj" : "Aktywuj"}
                  </button>
                  {category.count === 0 && (
                    <button className={"button"} type="button" disabled={busyId === category.id} onClick={() => remove(category)}>
                      Usuń
                    </button>
                  )}
                </span>
              </div>
            )}
          </li>
        ))}
      </ul>

      {!isLoading && !categories.length && (
        <p style={{ color: "#667" }}>Brak kategorii — dodaj pierwszą powyżej.</p>
      )}
    </div>
  );
};

export default ContactCategories;
