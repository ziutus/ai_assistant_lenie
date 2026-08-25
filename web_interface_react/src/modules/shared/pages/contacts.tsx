import React from "react";
import axios from "axios";
import { NavLink, useNavigate, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import type { ContactCategory } from "./contactCategories";
import type { ContactGroup } from "./contactGroups";

// Private contact book list (table `contacts`, GET /contacts) — independent
// of the NER persons registry (persons.tsx/organizations.tsx), see
// backend/library/contact_routes.py.

export interface ContactListItem {
  id: number;
  category_id: number;
  category_name: string | null;
  groups: { id: number; name: string }[];
  first_name: string | null;
  last_name: string;
  phone_number: string | null;
  email: string | null;
  has_whatsapp_profile: boolean;
  is_archived: boolean;
}

const PAGE_SIZE = 50;
const UNGROUPED_VALUE = "__ungrouped__";

const parseIdList = (value: string | null) =>
  (value ?? "").split(",").filter((id) => /^\d+$/.test(id));

const Contacts = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [contacts, setContacts] = React.useState<ContactListItem[]>([]);
  const [categories, setCategories] = React.useState<ContactCategory[]>([]);
  const [groups, setGroups] = React.useState<ContactGroup[]>([]);
  // Filters/offset are seeded from and kept in sync with the URL (same
  // pattern as list.tsx) so "Wróć do listy" — which round-trips a `list=`
  // param through the contact detail page — restores exactly what was
  // being viewed instead of resetting to an empty search.
  const [query, setQuery] = React.useState(searchParams.get("q") ?? "");
  const [categoryId, setCategoryId] = React.useState<string>(searchParams.get("category_id") ?? "");
  const [groupFilterActive, setGroupFilterActive] = React.useState(() => searchParams.has("group_filter") || searchParams.has("group_ids") || searchParams.has("group_id"));
  const [selectedGroupValues, setSelectedGroupValues] = React.useState<string[]>(() => [
    ...parseIdList(searchParams.get("group_ids") ?? searchParams.get("group_id")),
    ...(searchParams.get("include_ungrouped") === "1" ? [UNGROUPED_VALUE] : []),
  ]);
  const [archived, setArchived] = React.useState<string>(searchParams.get("archived") ?? "");
  const initialOffset = Number(searchParams.get("offset") ?? "0");
  const [offset, setOffset] = React.useState(Number.isFinite(initialOffset) && initialOffset > 0 ? initialOffset : 0);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const allGroupValues = [...groups.map((group) => String(group.id)), UNGROUPED_VALUE];
  const effectiveSelectedGroupValues = groupFilterActive ? selectedGroupValues : allGroupValues;
  const isAllGroupsSelected = effectiveSelectedGroupValues.length === allGroupValues.length
    && allGroupValues.every((value) => effectiveSelectedGroupValues.includes(value));

  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  const filterParams = (offsetArg: number) => {
    const params: Record<string, string> = {};
    if (query.trim()) params.q = query.trim();
    if (categoryId) params.category_id = categoryId;
    if (groupFilterActive && !isAllGroupsSelected) {
      params.group_filter = "1";
      const selectedGroupIds = effectiveSelectedGroupValues.filter((value) => value !== UNGROUPED_VALUE);
      if (selectedGroupIds.length) params.group_ids = selectedGroupIds.join(",");
      if (effectiveSelectedGroupValues.includes(UNGROUPED_VALUE)) params.include_ungrouped = "1";
    }
    if (archived) params.archived = archived;
    if (offsetArg) params.offset = String(offsetArg);
    return params;
  };
  const listQueryString = new URLSearchParams(filterParams(offset)).toString();
  const contactLinkSearch = listQueryString ? `?list=${encodeURIComponent(listQueryString)}` : "";

  const fetchCategories = async () => {
    try {
      const response = await axios.get(`${apiUrl}/contact_categories`, { headers });
      setCategories(response.data.contact_categories ?? []);
    } catch (error: any) {
      console.error("Error fetching contact categories", error);
    }
  };

  const fetchGroups = async () => {
    try {
      const response = await axios.get(`${apiUrl}/contact_groups`, { headers });
      setGroups(response.data.contact_groups ?? []);
    } catch (error: any) {
      console.error("Error fetching contact groups", error);
    }
  };

  const fetchContacts = async (offsetArg: number = 0) => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const params = { ...filterParams(offsetArg), offset: String(offsetArg), limit: String(PAGE_SIZE) };
      const response = await axios.get(`${apiUrl}/contacts`, { params, headers });
      const rows = response.data.contacts ?? [];
      setContacts(rows);
      setOffset(offsetArg);
      setTotal(response.data.total ?? rows.length);
      setSearchParams(filterParams(offsetArg), { replace: true });
      if (!rows.length) {
        setMessage("Brak kontaktów pasujących do filtrów.");
      }
    } catch (error: any) {
      console.error("Error fetching contacts", error);
      setIsError(true);
      setMessage(`Nie udało się pobrać kontaktów: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchCategories();
    fetchGroups();
    fetchContacts(offset);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = offset + contacts.length;

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Kontakty</h2>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          fetchContacts(0);
        }}
        style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}
      >
        <input
          type="text"
          value={query}
          placeholder="Szukaj po imieniu, nazwisku lub telefonie..."
          onChange={(e) => setQuery(e.target.value)}
          style={{ minWidth: 280, padding: "6px 10px" }}
          disabled={isLoading}
        />
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} style={{ padding: "6px 10px" }}>
          <option value="">Wszystkie kategorie</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <details style={{ position: "relative" }}>
          <summary style={{ cursor: "pointer", padding: "6px 10px", border: "1px solid #bbb", borderRadius: 3 }}>
            {isAllGroupsSelected ? "Wszystkie grupy" : `Grupy: wybrano ${effectiveSelectedGroupValues.length}`}
          </summary>
          <div style={{ position: "absolute", zIndex: 2, background: "white", border: "1px solid #bbb", borderRadius: 3, padding: 10, minWidth: 260, boxShadow: "0 2px 8px #0002" }}>
            <div style={{ fontSize: "0.85em", fontWeight: 600, marginBottom: 4 }}>Wybierz widoczne grupy:</div>
            <div style={{ display: "flex", gap: 6, marginBottom: 5 }}>
              <button type="button" className="button" onClick={() => { setGroupFilterActive(true); setSelectedGroupValues(allGroupValues); }}>Zaznacz wszystkie</button>
              <button type="button" className="button" onClick={() => { setGroupFilterActive(true); setSelectedGroupValues([]); }}>Odznacz wszystkie</button>
              <button type="button" className="button" onClick={() => { setGroupFilterActive(true); setSelectedGroupValues((values) => allGroupValues.filter((value) => !effectiveSelectedGroupValues.includes(value))); }}>Odwróć wybór</button>
            </div>
            {groups.map((g) => (
              <label key={`include-${g.id}`} style={{ display: "block", whiteSpace: "nowrap" }}>
                <input
                  type="checkbox"
                  checked={effectiveSelectedGroupValues.includes(String(g.id))}
                  onChange={(e) => { setGroupFilterActive(true); setSelectedGroupValues(e.target.checked ? [...effectiveSelectedGroupValues, String(g.id)] : effectiveSelectedGroupValues.filter((value) => value !== String(g.id))); }}
                /> {g.name}
              </label>
            ))}
            <label style={{ display: "block", whiteSpace: "nowrap", borderTop: "1px solid #ddd", marginTop: 8, paddingTop: 8 }}>
              <input
                type="checkbox"
                checked={effectiveSelectedGroupValues.includes(UNGROUPED_VALUE)}
                onChange={(e) => { setGroupFilterActive(true); setSelectedGroupValues(e.target.checked ? [...effectiveSelectedGroupValues, UNGROUPED_VALUE] : effectiveSelectedGroupValues.filter((value) => value !== UNGROUPED_VALUE)); }}
              /> (bez grupy)
            </label>
          </div>
        </details>
        <select value={archived} onChange={(e) => setArchived(e.target.value)} style={{ padding: "6px 10px" }}>
          <option value="">Aktywne</option>
          <option value="1">Zarchiwizowane</option>
          <option value="all">Wszystkie</option>
        </select>
        <button type="submit" className={"button"} disabled={isLoading}>
          Szukaj
        </button>
        <button
          type="button"
          className={"button"}
          style={{ marginLeft: "auto" }}
          onClick={() => navigate(`/contacts/new${contactLinkSearch}`)}
        >
          + Nowy kontakt
        </button>
      </form>

      {isLoading && <div className={"loader"}></div>}
      {message && (
        <p className={isError ? "errorText" : undefined} style={isError ? undefined : { color: "#667" }}>
          {message}
        </p>
      )}

      <ul style={{ listStyle: "none", padding: 0 }}>
        {contacts.map((contact) => (
          <li
            key={contact.id}
            style={{ padding: "8px 6px", borderBottom: "1px solid #eee", cursor: "pointer", display: "flex", gap: 12, alignItems: "center" }}
            onClick={() => navigate(`/contacts/${contact.id}${contactLinkSearch}`)}
          >
            <strong>{[contact.first_name, contact.last_name].filter(Boolean).join(" ")}</strong>
            {contact.is_archived && (
              <span style={{ fontSize: "0.8em", color: "#a33", border: "1px solid #e3a", borderRadius: 4, padding: "1px 6px" }}>
                archiwalny
              </span>
            )}
            {contact.has_whatsapp_profile && (
              <span title="Ma profil sąsiedzki zbudowany z WhatsApp">💬</span>
            )}
            {contact.phone_number && <span style={{ color: "#667" }}>{contact.phone_number}</span>}
            {contact.email && <span style={{ color: "#667" }}>{contact.email}</span>}
            {contact.groups.length > 0 && (
              <span style={{ marginLeft: "auto", display: "flex", gap: 4, flexWrap: "wrap" }}>
                {contact.groups.map((g) => (
                  <span
                    key={g.id}
                    style={{ fontSize: "0.8em", color: "#0369a1", background: "#e0f2fe", borderRadius: 4, padding: "1px 6px" }}
                  >
                    {g.name}
                  </span>
                ))}
              </span>
            )}
            {contact.category_name && (
              <span style={{ marginLeft: contact.groups.length > 0 ? undefined : "auto", fontSize: "0.85em", color: "#0369a1" }}>
                {contact.category_name}
              </span>
            )}
          </li>
        ))}
      </ul>

      {total > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 10 }}>
          <button
            type="button"
            className={"button"}
            disabled={isLoading || offset === 0}
            onClick={() => fetchContacts(Math.max(0, offset - PAGE_SIZE))}
          >
            ← Poprzednia
          </button>
          <span style={{ color: "#667", fontSize: "0.9em" }}>
            {pageStart}–{pageEnd} z {total}
          </span>
          <button
            type="button"
            className={"button"}
            disabled={isLoading || pageEnd >= total}
            onClick={() => fetchContacts(offset + PAGE_SIZE)}
          >
            Następna →
          </button>
        </div>
      )}

      <div style={{ marginTop: 14, display: "flex", gap: 16 }}>
        <NavLink to="/contact-categories" style={{ fontSize: "0.9em", color: "#0369a1" }}>
          Zarządzaj kategoriami kontaktów
        </NavLink>
        <NavLink to="/contact-groups" style={{ fontSize: "0.9em", color: "#0369a1" }}>
          Zarządzaj grupami kontaktów
        </NavLink>
      </div>
    </div>
  );
};

export default Contacts;
