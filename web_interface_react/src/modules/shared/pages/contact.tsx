import React from "react";
import axios from "axios";
import { useNavigate, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import type { ContactCategory } from "./contactCategories";
import type { ContactListItem } from "./contacts";

// Private contact detail/edit panel (`/contacts/:id`, id="new" for
// creation) — see backend/library/contact_routes.py.

interface ContactRelationship {
  id: number;
  direction: "outgoing" | "incoming";
  relationship_type: string;
  note: string | null;
  other_contact: { id: number; first_name: string | null; last_name: string };
}

interface ContactDetail {
  id: number;
  category_id: number;
  category_name: string | null;
  first_name: string | null;
  last_name: string;
  phone_number: string | null;
  email: string | null;
  linkedin_url: string | null;
  company: string | null;
  position: string | null;
  address: string | null;
  birthday: string | null;
  notes: string | null;
  relationships: ContactRelationship[];
}

const emptyForm = {
  category_id: "",
  first_name: "",
  last_name: "",
  phone_number: "",
  email: "",
  linkedin_url: "",
  company: "",
  position: "",
  address: "",
  birthday: "",
  notes: "",
};

const otherName = (other: { first_name: string | null; last_name: string }) =>
  [other.first_name, other.last_name].filter(Boolean).join(" ");

const Contact = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = id === "new";
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  const [form, setForm] = React.useState(emptyForm);
  const [categories, setCategories] = React.useState<ContactCategory[]>([]);
  const [relationships, setRelationships] = React.useState<ContactRelationship[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);

  const [relQuery, setRelQuery] = React.useState("");
  const [relResults, setRelResults] = React.useState<ContactListItem[]>([]);
  const [relTargetId, setRelTargetId] = React.useState<number | null>(null);
  const [relType, setRelType] = React.useState("");
  const [relNote, setRelNote] = React.useState("");

  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  const fetchCategories = async () => {
    try {
      const response = await axios.get(`${apiUrl}/contact_categories`, { params: { active: 1 }, headers });
      setCategories(response.data.contact_categories ?? []);
    } catch (error: any) {
      console.error("Error fetching contact categories", error);
    }
  };

  const loadContact = async () => {
    if (!id || isNew) return;
    setIsLoading(true);
    setMessage("");
    setIsError(false);
    try {
      const response = await axios.get(`${apiUrl}/contacts/${id}`, { headers });
      const contact: ContactDetail = response.data.contact;
      setForm({
        category_id: String(contact.category_id),
        first_name: contact.first_name ?? "",
        last_name: contact.last_name,
        phone_number: contact.phone_number ?? "",
        email: contact.email ?? "",
        linkedin_url: contact.linkedin_url ?? "",
        company: contact.company ?? "",
        position: contact.position ?? "",
        address: contact.address ?? "",
        birthday: contact.birthday ?? "",
        notes: contact.notes ?? "",
      });
      setRelationships(contact.relationships ?? []);
    } catch (error: any) {
      console.error("Error fetching contact", error);
      setIsError(true);
      setMessage(`Nie udało się pobrać kontaktu: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchCategories();
    setForm(emptyForm);
    setRelationships([]);
    loadContact();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const save = async () => {
    if (!form.last_name.trim()) {
      setIsError(true);
      setMessage("Nazwisko jest wymagane.");
      return;
    }
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    const payload = {
      ...form,
      category_id: form.category_id ? Number(form.category_id) : undefined,
      birthday: form.birthday || null,
    };
    try {
      if (isNew) {
        const response = await axios.post(`${apiUrl}/contacts`, payload, { headers });
        setMessage("Zapisano kontakt.");
        navigate(`/contacts/${response.data.contact.id}`, { replace: true });
      } else {
        await axios.patch(`${apiUrl}/contacts/${id}`, payload, { headers });
        setMessage("Zapisano zmiany.");
      }
    } catch (error: any) {
      console.error("Error saving contact", error);
      setIsError(true);
      setMessage(`Nie udało się zapisać: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  const remove = async () => {
    if (isNew || !window.confirm(`Usunąć kontakt „${form.first_name} ${form.last_name}”?`)) return;
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/contacts/${id}`, { headers });
      navigate("/contacts");
    } catch (error: any) {
      console.error("Error deleting contact", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  const searchRelTargets = async () => {
    try {
      const response = await axios.get(`${apiUrl}/contacts`, {
        params: relQuery.trim() ? { q: relQuery.trim() } : {}, headers,
      });
      const found = (response.data.contacts ?? []).filter((c: ContactListItem) => String(c.id) !== id);
      setRelResults(found);
    } catch (error: any) {
      console.error("Error searching contacts for relationship", error);
    }
  };

  const addRelationship = async () => {
    if (!relTargetId || !relType.trim()) {
      setIsError(true);
      setMessage("Wybierz kontakt i podaj typ powiązania.");
      return;
    }
    setIsError(false);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/contacts/${id}/relationships`, {
        related_contact_id: relTargetId, relationship_type: relType.trim(), note: relNote.trim() || undefined,
      }, { headers });
      setRelType("");
      setRelNote("");
      setRelTargetId(null);
      setRelQuery("");
      setRelResults([]);
      loadContact();
    } catch (error: any) {
      console.error("Error adding relationship", error);
      setIsError(true);
      setMessage(`Nie udało się dodać powiązania: ${error.response?.data?.message || error.message}`);
    }
  };

  const removeRelationship = async (relationshipId: number) => {
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/contact_relationships/${relationshipId}`, { headers });
      loadContact();
    } catch (error: any) {
      console.error("Error deleting relationship", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć powiązania: ${error.response?.data?.message || error.message}`);
    }
  };

  const inputStyle: React.CSSProperties = { padding: "6px 10px", width: "100%", boxSizing: "border-box" };
  const outgoing = relationships.filter((r) => r.direction === "outgoing");
  const incoming = relationships.filter((r) => r.direction === "incoming");

  return (
    <div style={{ maxWidth: 560 }}>
      <h2 style={{ marginBottom: "10px" }}>{isNew ? "Nowy kontakt" : "Kontakt"}</h2>

      {isLoading && <div className={"loader"}></div>}
      {message && (
        <p className={isError ? "errorText" : undefined} style={isError ? undefined : { color: "#2e7d43" }}>
          {message}
        </p>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label>
          Imię
          <input type="text" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} style={inputStyle} />
        </label>
        <label>
          Nazwisko *
          <input type="text" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} style={inputStyle} />
        </label>
        <label>
          Telefon
          <input type="text" value={form.phone_number} onChange={(e) => setForm({ ...form, phone_number: e.target.value })} style={inputStyle} />
        </label>
        <label>
          Email
          <input type="text" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} style={inputStyle} />
        </label>
        <label>
          LinkedIn
          <input type="text" value={form.linkedin_url} onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })} style={inputStyle} />
        </label>
        <label>
          Firma
          <input type="text" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} style={inputStyle} />
        </label>
        <label>
          Stanowisko
          <input type="text" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} style={inputStyle} />
        </label>
        <label>
          Adres
          <input type="text" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} style={inputStyle} />
        </label>
        <label>
          Urodziny
          <input type="date" value={form.birthday} onChange={(e) => setForm({ ...form, birthday: e.target.value })} style={inputStyle} />
        </label>
        <label>
          Kategoria
          <select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} style={inputStyle}>
            <option value="">(domyślna)</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label>
          Notatki
          <textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={3} style={inputStyle} />
        </label>

        <div style={{ display: "flex", gap: 8 }}>
          <button className={"button"} type="button" disabled={isLoading} onClick={save}>
            Zapisz
          </button>
          {!isNew && (
            <button className={"button"} type="button" disabled={isLoading} onClick={remove}>
              Usuń
            </button>
          )}
          <button className={"button"} type="button" onClick={() => navigate("/contacts")}>
            ← Wróć do listy
          </button>
        </div>
      </div>

      {!isNew && (
        <div style={{ marginTop: 24 }}>
          <h3>Powiązania</h3>
          {outgoing.length === 0 && incoming.length === 0 && (
            <p style={{ color: "#667" }}>Brak zapisanych powiązań.</p>
          )}
          {outgoing.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {outgoing.map((r) => (
                <li key={r.id} style={{ padding: "4px 0" }}>
                  <strong>{otherName(r.other_contact)}</strong> — {r.relationship_type}
                  {r.note && <span style={{ color: "#667" }}> ({r.note})</span>}
                  <button
                    type="button"
                    onClick={() => removeRelationship(r.id)}
                    style={{ marginLeft: 8, border: "none", background: "none", color: "#a33", cursor: "pointer" }}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
          {incoming.length > 0 && (
            <>
              <div style={{ marginTop: 8, color: "#667", fontSize: "0.9em" }}>Kto się z Tobą łączy:</div>
              <ul style={{ listStyle: "none", padding: 0 }}>
                {incoming.map((r) => (
                  <li key={r.id} style={{ padding: "4px 0" }}>
                    <strong>{otherName(r.other_contact)}</strong> — {r.relationship_type}
                    {r.note && <span style={{ color: "#667" }}> ({r.note})</span>}
                  </li>
                ))}
              </ul>
            </>
          )}

          <div style={{ marginTop: 12, padding: 8, background: "#f5f7fa", border: "1px solid #d5dde8", borderRadius: 6 }}>
            <div style={{ marginBottom: 6, color: "#667", fontSize: "0.9em" }}>Dodaj powiązanie:</div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <input
                type="text"
                value={relQuery}
                placeholder="Szukaj kontaktu..."
                onChange={(e) => setRelQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    searchRelTargets();
                  }
                }}
                style={{ minWidth: 200, padding: "4px 8px" }}
              />
              <button className={"button"} type="button" onClick={searchRelTargets}>Szukaj</button>
            </div>
            {relResults.length > 0 && (
              <select
                value={relTargetId ?? ""}
                onChange={(e) => setRelTargetId(Number(e.target.value))}
                style={{ marginTop: 6, padding: "4px 8px", minWidth: 220 }}
              >
                <option value="">Wybierz kontakt...</option>
                {relResults.map((c) => (
                  <option key={c.id} value={c.id}>{[c.first_name, c.last_name].filter(Boolean).join(" ")}</option>
                ))}
              </select>
            )}
            <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
              <input
                type="text"
                value={relType}
                placeholder="Typ powiązania (np. żona, syn, przyjaciel)"
                onChange={(e) => setRelType(e.target.value)}
                style={{ padding: "4px 8px", minWidth: 200 }}
              />
              <input
                type="text"
                value={relNote}
                placeholder="Notatka (opcjonalnie)"
                onChange={(e) => setRelNote(e.target.value)}
                style={{ padding: "4px 8px", minWidth: 160 }}
              />
              <button className={"button"} type="button" onClick={addRelationship}>Dodaj powiązanie</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Contact;
