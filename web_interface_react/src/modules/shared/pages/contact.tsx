import React from "react";
import axios from "axios";
import { useNavigate, useParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import type { ContactCategory } from "./contactCategories";
import type { ContactGroup } from "./contactGroups";
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

type OrgType = "employment" | "jdg" | "board" | "ownership" | "other";
type OrgStatus = "candidate" | "confirmed" | "rejected";

interface ContactOrganization {
  id: number;
  org_type: OrgType;
  organization_name: string;
  role: string | null;
  nip: string | null;
  regon: string | null;
  address: string | null;
  is_primary: boolean;
  is_current: boolean;
  start_date: string | null;
  end_date: string | null;
  status: OrgStatus;
  source_url: string | null;
  notes: string | null;
}

const ORG_TYPE_LABELS: Record<OrgType, string> = {
  employment: "Etat",
  jdg: "JDG (własna działalność)",
  board: "Funkcja w zarządzie",
  ownership: "Udziały / współwłasność",
  other: "Inne",
};

const ORG_STATUS_LABELS: Record<OrgStatus, string> = {
  candidate: "niepotwierdzone",
  confirmed: "potwierdzone",
  rejected: "odrzucone",
};

const emptyOrgForm = {
  org_type: "jdg" as OrgType,
  organization_name: "",
  role: "",
  nip: "",
  regon: "",
  address: "",
  is_primary: false,
  is_current: true,
  status: "candidate" as OrgStatus,
  source_url: "",
  notes: "",
};

interface ContactDetail {
  id: number;
  category_id: number;
  category_name: string | null;
  groups: { id: number; name: string }[];
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
  organizations: ContactOrganization[];
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

// CEIDG (Centralna Ewidencja i Informacja o Działalności Gospodarczej) — the
// official Polish government JDG register, the authoritative source to
// verify a sole-proprietorship candidate against (vs. the aggregator
// mirrors — Panorama Firm, Aleo, GoWork — that OSINT search tends to find).
const ceidgUrlForNip = (nip: string) =>
  `https://aplikacja.ceidg.gov.pl/ceidg/ceidg.public.ui/searchdetails.aspx?Nip=${encodeURIComponent(nip.replace(/[^0-9]/g, ""))}`;

const Contact = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = id === "new";
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);

  const [form, setForm] = React.useState(emptyForm);
  const [categories, setCategories] = React.useState<ContactCategory[]>([]);
  const [allGroups, setAllGroups] = React.useState<ContactGroup[]>([]);
  const [contactGroups, setContactGroups] = React.useState<{ id: number; name: string }[]>([]);
  const [groupToAdd, setGroupToAdd] = React.useState<string>("");
  const [relationships, setRelationships] = React.useState<ContactRelationship[]>([]);
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);

  const [relQuery, setRelQuery] = React.useState("");
  const [relResults, setRelResults] = React.useState<ContactListItem[]>([]);
  const [relTargetId, setRelTargetId] = React.useState<number | null>(null);
  const [relType, setRelType] = React.useState("");
  const [relNote, setRelNote] = React.useState("");

  const [organizations, setOrganizations] = React.useState<ContactOrganization[]>([]);
  const [orgForm, setOrgForm] = React.useState(emptyOrgForm);
  const [showOrgForm, setShowOrgForm] = React.useState(false);

  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  const fetchCategories = async () => {
    try {
      const response = await axios.get(`${apiUrl}/contact_categories`, { params: { active: 1 }, headers });
      setCategories(response.data.contact_categories ?? []);
    } catch (error: any) {
      console.error("Error fetching contact categories", error);
    }
  };

  const fetchAllGroups = async () => {
    try {
      const response = await axios.get(`${apiUrl}/contact_groups`, { headers });
      setAllGroups(response.data.contact_groups ?? []);
    } catch (error: any) {
      console.error("Error fetching contact groups", error);
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
      setOrganizations(contact.organizations ?? []);
      setContactGroups(contact.groups ?? []);
    } catch (error: any) {
      console.error("Error fetching contact", error);
      setIsError(true);
      setMessage(`Nie udało się pobrać kontaktu: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchCategories();
    fetchAllGroups();
    setForm(emptyForm);
    setRelationships([]);
    setOrganizations([]);
    setContactGroups([]);
    loadContact();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const addGroup = async () => {
    if (!groupToAdd) return;
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/contacts/${id}/groups`, { group_id: Number(groupToAdd) }, { headers });
      setContactGroups(response.data.contact.groups ?? []);
      setGroupToAdd("");
    } catch (error: any) {
      console.error("Error adding contact to group", error);
      setIsError(true);
      setMessage(`Nie udało się dodać do grupy: ${error.response?.data?.message || error.message}`);
    }
  };

  const removeGroup = async (groupId: number) => {
    setIsError(false);
    setMessage("");
    try {
      const response = await axios.delete(`${apiUrl}/contacts/${id}/groups/${groupId}`, { headers });
      setContactGroups(response.data.contact.groups ?? []);
    } catch (error: any) {
      console.error("Error removing contact from group", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć z grupy: ${error.response?.data?.message || error.message}`);
    }
  };

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

  const addOrganization = async () => {
    if (!orgForm.organization_name.trim()) {
      setIsError(true);
      setMessage("Podaj nazwę organizacji.");
      return;
    }
    setIsError(false);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/contacts/${id}/organizations`, {
        org_type: orgForm.org_type,
        organization_name: orgForm.organization_name.trim(),
        role: orgForm.role.trim() || undefined,
        nip: orgForm.nip.trim() || undefined,
        regon: orgForm.regon.trim() || undefined,
        address: orgForm.address.trim() || undefined,
        is_primary: orgForm.is_primary,
        is_current: orgForm.is_current,
        status: orgForm.status,
        source_url: orgForm.source_url.trim() || undefined,
        notes: orgForm.notes.trim() || undefined,
      }, { headers });
      setOrgForm(emptyOrgForm);
      setShowOrgForm(false);
      loadContact();
    } catch (error: any) {
      console.error("Error adding organization", error);
      setIsError(true);
      setMessage(`Nie udało się dodać organizacji: ${error.response?.data?.message || error.message}`);
    }
  };

  const updateOrganizationStatus = async (organizationId: number, status: OrgStatus) => {
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/contact_organizations/${organizationId}`, { status }, { headers });
      loadContact();
    } catch (error: any) {
      console.error("Error updating organization", error);
      setIsError(true);
      setMessage(`Nie udało się zaktualizować organizacji: ${error.response?.data?.message || error.message}`);
    }
  };

  const removeOrganization = async (organizationId: number) => {
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/contact_organizations/${organizationId}`, { headers });
      loadContact();
    } catch (error: any) {
      console.error("Error deleting organization", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć organizacji: ${error.response?.data?.message || error.message}`);
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

        {!isNew && (
          <div>
            <div style={{ marginBottom: 4 }}>Grupy</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
              {contactGroups.length === 0 && <span style={{ color: "#667" }}>Brak grup.</span>}
              {contactGroups.map((g) => (
                <span
                  key={g.id}
                  style={{
                    display: "flex", alignItems: "center", gap: 4, fontSize: "0.85em", color: "#0369a1",
                    background: "#e0f2fe", borderRadius: 4, padding: "2px 6px",
                  }}
                >
                  {g.name}
                  <button
                    type="button"
                    onClick={() => removeGroup(g.id)}
                    style={{ border: "none", background: "none", color: "#0369a1", cursor: "pointer", padding: 0, lineHeight: 1 }}
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <select value={groupToAdd} onChange={(e) => setGroupToAdd(e.target.value)} style={{ padding: "4px 8px", flex: 1 }}>
                <option value="">Dodaj do grupy...</option>
                {allGroups
                  .filter((g) => !contactGroups.some((cg) => cg.id === g.id))
                  .map((g) => (
                    <option key={g.id} value={g.id}>{g.name}</option>
                  ))}
              </select>
              <button className={"button"} type="button" disabled={!groupToAdd} onClick={addGroup}>
                Dodaj
              </button>
            </div>
          </div>
        )}

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
          <h3>Organizacje (etat, JDG, funkcje...)</h3>
          <p style={{ color: "#667", fontSize: "0.85em", marginTop: -6 }}>
            Jedna osoba może mieć kilka afiliacji naraz — np. etat gdzie indziej i osobną JDG do optymalizacji
            podatkowej. Adres tutaj to adres rejestrowy tej organizacji, nie adres zamieszkania kontaktu.
          </p>
          {organizations.length === 0 && (
            <p style={{ color: "#667" }}>Brak zapisanych organizacji.</p>
          )}
          {organizations.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {organizations.map((org) => (
                <li
                  key={org.id}
                  style={{
                    padding: "8px 10px", marginBottom: 6, borderRadius: 6,
                    background: org.status === "candidate" ? "#fff8e6" : "#f5f7fa",
                    border: `1px solid ${org.status === "candidate" ? "#e8d18a" : "#d5dde8"}`,
                  }}
                >
                  <div>
                    <strong>{org.organization_name}</strong>
                    {" — "}
                    {ORG_TYPE_LABELS[org.org_type]}
                    {org.role && <span> ({org.role})</span>}
                    {org.is_primary && <span title="Główna afiliacja"> ⭐</span>}
                    {!org.is_current && <span style={{ color: "#a33" }}> [nieaktualne]</span>}
                    <span style={{ marginLeft: 8, fontSize: "0.8em", color: "#667" }}>
                      [{ORG_STATUS_LABELS[org.status]}]
                    </span>
                  </div>
                  {(org.nip || org.regon) && (
                    <div style={{ fontSize: "0.85em", color: "#667" }}>
                      {org.nip && <span>NIP: {org.nip} </span>}
                      {org.regon && <span>REGON: {org.regon}</span>}
                    </div>
                  )}
                  {org.address && <div style={{ fontSize: "0.85em", color: "#667" }}>{org.address}</div>}
                  {org.notes && <div style={{ fontSize: "0.85em", color: "#667" }}>{org.notes}</div>}
                  <div style={{ marginTop: 4, display: "flex", gap: 8, alignItems: "center" }}>
                    {org.nip && (
                      <a
                        href={ceidgUrlForNip(org.nip)}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="Sprawdź w oficjalnym rejestrze CEIDG"
                        style={{ color: "#2b6cb0" }}
                      >
                        Sprawdź w CEIDG ↗
                      </a>
                    )}
                    {org.status === "candidate" && (
                      <>
                        <button
                          type="button"
                          onClick={() => updateOrganizationStatus(org.id, "confirmed")}
                          style={{ border: "none", background: "none", color: "#2e7d43", cursor: "pointer", padding: 0 }}
                        >
                          ✓ Potwierdź
                        </button>
                        <button
                          type="button"
                          onClick={() => updateOrganizationStatus(org.id, "rejected")}
                          style={{ border: "none", background: "none", color: "#a33", cursor: "pointer", padding: 0 }}
                        >
                          ✕ Odrzuć
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => removeOrganization(org.id)}
                      style={{ border: "none", background: "none", color: "#a33", cursor: "pointer", padding: 0 }}
                    >
                      Usuń
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {!showOrgForm && (
            <button className={"button"} type="button" onClick={() => setShowOrgForm(true)}>
              + Dodaj organizację
            </button>
          )}
          {showOrgForm && (
            <div style={{ marginTop: 8, padding: 8, background: "#f5f7fa", border: "1px solid #d5dde8", borderRadius: 6 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <select
                  value={orgForm.org_type}
                  onChange={(e) => setOrgForm({ ...orgForm, org_type: e.target.value as OrgType })}
                  style={{ padding: "4px 8px" }}
                >
                  {(Object.keys(ORG_TYPE_LABELS) as OrgType[]).map((t) => (
                    <option key={t} value={t}>{ORG_TYPE_LABELS[t]}</option>
                  ))}
                </select>
                <input
                  type="text" placeholder="Nazwa organizacji *" value={orgForm.organization_name}
                  onChange={(e) => setOrgForm({ ...orgForm, organization_name: e.target.value })}
                  style={{ padding: "4px 8px", minWidth: 220 }}
                />
                <input
                  type="text" placeholder="Rola / stanowisko" value={orgForm.role}
                  onChange={(e) => setOrgForm({ ...orgForm, role: e.target.value })}
                  style={{ padding: "4px 8px", minWidth: 160 }}
                />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                <input
                  type="text" placeholder="NIP" value={orgForm.nip}
                  onChange={(e) => setOrgForm({ ...orgForm, nip: e.target.value })}
                  style={{ padding: "4px 8px", width: 130 }}
                />
                <input
                  type="text" placeholder="REGON" value={orgForm.regon}
                  onChange={(e) => setOrgForm({ ...orgForm, regon: e.target.value })}
                  style={{ padding: "4px 8px", width: 130 }}
                />
                <input
                  type="text" placeholder="Adres rejestrowy organizacji" value={orgForm.address}
                  onChange={(e) => setOrgForm({ ...orgForm, address: e.target.value })}
                  style={{ padding: "4px 8px", minWidth: 220 }}
                />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
                <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <input
                    type="checkbox" checked={orgForm.is_primary}
                    onChange={(e) => setOrgForm({ ...orgForm, is_primary: e.target.checked })}
                  />
                  Główna afiliacja
                </label>
                <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <input
                    type="checkbox" checked={orgForm.is_current}
                    onChange={(e) => setOrgForm({ ...orgForm, is_current: e.target.checked })}
                  />
                  Aktualne
                </label>
                <select
                  value={orgForm.status}
                  onChange={(e) => setOrgForm({ ...orgForm, status: e.target.value as OrgStatus })}
                  style={{ padding: "4px 8px" }}
                >
                  {(Object.keys(ORG_STATUS_LABELS) as OrgStatus[]).map((s) => (
                    <option key={s} value={s}>{ORG_STATUS_LABELS[s]}</option>
                  ))}
                </select>
              </div>
              <input
                type="text" placeholder="Źródło (URL)" value={orgForm.source_url}
                onChange={(e) => setOrgForm({ ...orgForm, source_url: e.target.value })}
                style={{ padding: "4px 8px", marginTop: 6, width: "100%", boxSizing: "border-box" }}
              />
              <textarea
                placeholder="Notatki" value={orgForm.notes} rows={2}
                onChange={(e) => setOrgForm({ ...orgForm, notes: e.target.value })}
                style={{ padding: "4px 8px", marginTop: 6, width: "100%", boxSizing: "border-box" }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                <button className={"button"} type="button" onClick={addOrganization}>Zapisz organizację</button>
                <button className={"button"} type="button" onClick={() => { setShowOrgForm(false); setOrgForm(emptyOrgForm); }}>
                  Anuluj
                </button>
              </div>
            </div>
          )}
        </div>
      )}

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
