import ContactChannelsEditor, { type ContactChannel } from "../components/ContactChannelsEditor";
import ContactInterestsEducation from "../components/ContactInterestsEducation";
import React from "react";
import axios from "axios";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import type { ContactCategory } from "./contactCategories";
import type { ContactGroupEvent } from "./contactGroupDetail";
import type { ContactGroup } from "./contactGroups";
import type { ContactListItem } from "./contacts";
import ContactPhotoDescriptions, { type ContactPhotoData } from "../components/ContactPhotoDescriptions";
import ContactPhotoHistory from "../components/ContactPhotoHistory";
import ContactFamilyForm from "../components/ContactFamilyForm";

const CountryMap = React.lazy(() => import("../components/CountryMap/countryMap"));

// Private contact detail/edit panel (`/contacts/:id`, id="new" for
// creation) — see backend/library/contact_routes.py.

interface ContactRelationship {
  id: number;
  direction: "outgoing" | "incoming";
  relationship_type: string;
  note: string | null;
  start_date: string | null;
  end_date: string | null;
  other_contact: { id: number; first_name: string | null; last_name: string | null; display_name?: string };
}

interface WhatsappFact {
  wartosc?: string;
  co?: string;
  gdzie?: string;
  kiedy?: string;
  zrodlo?: string | null;
}

interface WhatsappProfileFacts {
  zawod_lub_branza: WhatsappFact | null;
  miejsce_pracy: WhatsappFact | null;
  hobby_zainteresowania: WhatsappFact[];
  zwierzeta: WhatsappFact[];
  dzieci: WhatsappFact | null;
  urodziny: WhatsappFact | null;
  podroze_wakacje: WhatsappFact[];
  wydarzenia_ostatnie: WhatsappFact[];
  zaangazowanie_osiedlowe: WhatsappFact | null;
}

interface WhatsappProfileGroupStats {
  group_label: string;
  last_processed_at: string;
  message_count: number;
  first_date: string;
  last_date: string;
}

interface WhatsappProfile {
  profile: WhatsappProfileFacts | null;
  suggestions: string[];
  groups: Record<string, WhatsappProfileGroupStats>;
}

type OrgType = "employment" | "jdg" | "board" | "ownership" | "other";
type OrgStatus = "candidate" | "confirmed" | "rejected";

type LookupType = "phone" | "linkedin" | "web" | "email";
type LookupStatus = "no_results" | "candidate" | "confirmed" | "rejected";

interface Address {
  id: number;
  label: string | null;
  notes: string | null;
  street: string | null;
  building_number: string | null;
  block_number: string | null;
  apartment_number: string | null;
  postal_code: string | null;
  city: string;
  country: string | null;
  formatted_address: string;
  latitude: number | null;
  longitude: number | null;
  geocoded: boolean;
  verified_at: string | null;
}

interface AddressValidationResult {
  outcome: "confirmed" | "not_found" | "unavailable";
  official_postal_code: string | null;
  postal_code_matches: boolean | null;
  score: number | null;
  osm_supplement?: {
    found: boolean;
    postal_code: string | null;
    nearby_postal_code?: string | null;
    housename?: string | null;
    lat?: number | null;
    lon?: number | null;
    osm_id?: number;
    osm_type?: string;
  } | null;
  address: Address;
}

interface ContactAddress {
  id: number;
  role: string | null;
  is_primary: boolean;
  address: Address;
}

interface AddressSearchResult extends Address {
  linked_contacts: { id: number; display_name: string }[];
}

const addressFields = [
  { key: "street", label: "Ulica", maxLength: 200 },
  { key: "building_number", label: "Nr budynku", maxLength: 20 },
  { key: "block_number", label: "Nr bloku", maxLength: 20 },
  { key: "apartment_number", label: "Nr lokalu", maxLength: 20 },
  { key: "postal_code", label: "Kod pocztowy", maxLength: 10 },
  { key: "city", label: "Miasto / miejscowość", maxLength: 200 },
  { key: "country", label: "Kraj", maxLength: 100 },
] as const;
type ParsedAddress = { [Key in typeof addressFields[number]["key"] | "notes"]: string | null };
const ADDRESS_NOTES_MAX_LENGTH = 1000;
const emptyAddressForm = {
  label: "", street: "", building_number: "", block_number: "", apartment_number: "", postal_code: "", city: "", country: "Polska",
  role: "zamieszkania", is_primary: false, notes: "",
};

interface ContactOrganization {
  id: number;
  org_type: OrgType;
  organization_name: string;
  role: string | null;
  nip: string | null;
  regon: string | null;
  address: string | null;
  correspondence_address: string | null;
  website: string | null;
  is_primary: boolean;
  is_current: boolean;
  start_date: string | null;
  end_date: string | null;
  suspended_at: string | null;
  verified_at: string | null;
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

interface ContactLookupResult {
  id: number;
  lookup_type: LookupType;
  status: LookupStatus;
  url: string | null;
  query_used: string | null;
  notes: string | null;
  searched_at: string;
}

const LOOKUP_TYPE_LABELS: Record<LookupType, string> = {
  phone: "Telefon",
  linkedin: "LinkedIn",
  web: "Wyszukiwanie w sieci",
  email: "E-mail",
};

const LOOKUP_STATUS_LABELS: Record<LookupStatus, string> = {
  no_results: "brak wyników",
  candidate: "niepotwierdzone",
  confirmed: "potwierdzone",
  rejected: "odrzucone",
};

const ORG_STATUS_LABELS: Record<OrgStatus, string> = {
  candidate: "niepotwierdzone",
  confirmed: "potwierdzone",
  rejected: "odrzucone",
};

type LinkType = "linkedin" | "facebook" | "instagram" | "twitter" | "website" | "fixly" | "other";

interface ContactLink {
  id: number;
  link_type: LinkType;
  url: string;
  label: string | null;
}

const LINK_TYPE_LABELS: Record<LinkType, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
  instagram: "Instagram",
  twitter: "X / Twitter",
  website: "Strona WWW",
  fixly: "Fixly",
  other: "Inne",
};

type CefrLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2";
const LANGUAGE_LEVELS: CefrLevel[] = ["A1", "A2", "B1", "B2", "C1", "C2"];

interface ContactLanguage {
  language: string;
  native: boolean;
  level: CefrLevel | null;
}

const languageSummary = (lang: ContactLanguage) =>
  lang.native ? `${lang.language} (native speaker)` : lang.level ? `${lang.language} (${lang.level})` : lang.language;

type ChangeSource = "manual_edit" | "google_import" | "linkedin_analysis" | "whatsapp_analysis" | "osint_lookup" | "other";

interface ContactChangeLogEntry {
  id: number;
  source: ChangeSource;
  changed_fields: string[];
  note: string | null;
  created_at: string;
}

const CHANGE_SOURCE_LABELS: Record<ChangeSource, string> = {
  manual_edit: "Ręczna edycja",
  google_import: "Import Kontaktów Google",
  linkedin_analysis: "Analiza LinkedIn",
  whatsapp_analysis: "Analiza WhatsApp",
  osint_lookup: "Wyszukiwanie OSINT",
  other: "Inne",
};

const MONTHS_GENITIVE = [
  "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
  "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
];

type Gender = "male" | "female" | "other";

const GENDER_LABELS: Record<Gender, string> = {
  male: "Mężczyzna",
  female: "Kobieta",
  other: "Inna",
};

const CHANGE_FIELD_LABELS: Record<string, string> = {
  first_name: "Imię",
  last_name: "Nazwisko",
  gender: "Płeć",
  display_label: "Nazwa robocza",
  phone_number: "Telefon",
  email: "Email",
  phone_numbers: "Telefony",
  email_addresses: "Adresy e-mail",
  linkedin_url: "LinkedIn",
  links: "Linki",
  company: "Firma",
  position: "Stanowisko",
  addresses: "Adresy",
  current_city: "Mieszka w",
  hometown: "Pochodzi z",
  birthday: "Urodziny",
  pesel: "PESEL",
  notes: "Notatki",
  languages: "Języki",
  nationality: "Narodowość",
  category_id: "Kategoria",
  is_archived: "Status archiwizacji",
  whatsapp_profile: "Profil WhatsApp",
  groups: "Grupy",
  interests: "Zainteresowania",
  education: "Wykształcenie",
  photo_storage_key: "Zdjęcie",
  photo_user_description: "Twój opis zdjęcia",
  photo_ai_description: "Opis zdjęcia AI",
};

const changeFieldLabel = (field: string) => CHANGE_FIELD_LABELS[field] ?? field;

const emptyOrgForm = {
  org_type: "jdg" as OrgType,
  organization_name: "",
  role: "",
  nip: "",
  regon: "",
  address: "",
  correspondence_address: "",
  website: "",
  is_primary: false,
  is_current: true,
  status: "candidate" as OrgStatus,
  source_url: "",
  notes: "",
  suspended_at: "",
  verified_at: "",
};

const emptyLookupForm = {
  lookup_type: "email" as LookupType,
  status: "candidate" as LookupStatus,
  url: "",
  query_used: "",
  notes: "",
};

const emptyLinkForm = {
  link_type: "facebook" as LinkType,
  url: "",
  label: "",
};

interface ChatConversationSummary {
  id: number;
  display_name: string;
  platform: string;
  message_count: number;
  last_message_at: string | null;
}

interface ContactDetail {
  id: number;
  category_id: number;
  category_name: string | null;
  groups: { id: number; name: string }[];
  first_name: string | null;
  last_name: string | null;
  gender: Gender | null;
  display_label: string | null;
  display_name: string;
  phone_number: string | null;
  email: string | null;
  phone_numbers?: ContactChannel[];
  email_addresses?: ContactChannel[];
  company: string | null;
  position: string | null;
  addresses: ContactAddress[];
  current_city: string | null;
  hometown: string | null;
  birthday: string | null;
  birthday_month: number | null;
  birthday_day: number | null;
  pesel: string | null;
  notes: string | null;
  languages: ContactLanguage[];
  nationality: string[];
  is_archived: boolean;
  relationships: ContactRelationship[];
  organizations: ContactOrganization[];
  lookup_results: ContactLookupResult[];
  links: ContactLink[];
  events: ContactGroupEvent[];
  change_log: ContactChangeLogEntry[];
  whatsapp_profile: WhatsappProfile | null;
  chat_conversations: ChatConversationSummary[];
  photo_url: string | null;
  photo: ContactPhotoData | null;
}

const emptyForm = {
  category_id: "",
  first_name: "",
  last_name: "",
  gender: "" as Gender | "",
  display_label: "",
  phone_numbers: [] as ContactChannel[],
  email_addresses: [] as ContactChannel[],
  company: "",
  position: "",
  current_city: "",
  hometown: "",
  birthday: "",
  birthday_month: "",
  birthday_day: "",
  pesel: "",
  notes: "",
  languages: [] as ContactLanguage[],
  nationality: [] as string[],
};

const otherName = (other: { first_name: string | null; last_name: string | null; display_name?: string }) =>
  other.display_name || [other.first_name, other.last_name].filter(Boolean).join(" ");

const relDatesLabel = (r: ContactRelationship) => {
  if (!r.start_date && !r.end_date) return null;
  return `${r.start_date ?? "?"} – ${r.end_date ?? "nadal"}`;
};

// events arrives sorted event_date desc, id desc (see GET /contacts/:id
// in contact_routes.py) — the first entry is always the most recent one.
const latestEvent = (events: ContactGroupEvent[] | undefined) =>
  events && events.length > 0 ? events[0] : null;

const eventHintText = (event: ContactGroupEvent) =>
  event.group_name
    ? `${event.group_name}: „${event.title}” (${event.event_date})`
    : `„${event.title}” (${event.event_date})`;

// CEIDG (Centralna Ewidencja i Informacja o Działalności Gospodarczej) — the
// official Polish government JDG register, the authoritative source to
// verify a sole-proprietorship candidate against (vs. the aggregator
// mirrors — Panorama Firm, Aleo, GoWork — that OSINT search tends to find).
const ceidgUrlForNip = (nip: string) =>
  `https://aplikacja.ceidg.gov.pl/ceidg/ceidg.public.ui/searchdetails.aspx?Nip=${encodeURIComponent(nip.replace(/[^0-9]/g, ""))}`;

// Free-text fields (contact/organization notes) sometimes carry a raw URL
// typed by hand (e.g. "Facebook: https://..."). Render it as a clickable
// link instead of plain text, same trailing-punctuation handling as
// read.tsx's renderInline bareUrl case — kept separate here since that
// function also does markdown/wikilink/footnote parsing this plain text
// doesn't need.
//
// Also links a scheme-less host after "www:" (CEIDG-imported organization
// notes read "www: kraton.pl") — https:// is prepended for the href.
const linkifyPlainText = (text: string): React.ReactNode[] =>
  text.split(/(https?:\/\/[^\s)]+|(?<=www:\s*)[^\s,;)]+)/gi).map((part, i) => {
    const match = part.match(/^([^\s)]+?)([.,;:!?]*)$/);
    const isUrl = match && (/^https?:\/\//i.test(part) || (i % 2 === 1));
    if (!match || !isUrl) return <React.Fragment key={i}>{part}</React.Fragment>;
    const [, url, trailing] = match;
    const href = /^https?:\/\//i.test(url) ? url : `https://${url}`;
    return (
      <React.Fragment key={i}>
        <a href={href} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all" }}>{url}</a>
        {trailing}
      </React.Fragment>
    );
  });

const Contact = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isNew = id === "new";
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  // Round-tripped from contacts.tsx (`?list=<encoded querystring>`, same
  // pattern as read.tsx/list.tsx) so "Wróć do listy" restores the search/
  // filters/pagination the user came from instead of resetting them.
  const listContext = searchParams.get("list") ?? "";
  const backToListUrl = `/contacts${listContext ? `?${listContext}` : ""}`;

  // Default view is read-only; "Edytuj" switches to the always-editable form
  // that used to be the only view. /contacts/new always starts (and stays)
  // in edit mode since there's nothing yet to display read-only.
  const [mode, setMode] = React.useState<"view" | "edit">(isNew ? "edit" : "view");
  const [contact, setContact] = React.useState<ContactDetail | null>(null);
  const [form, setForm] = React.useState(emptyForm);
  const [categories, setCategories] = React.useState<ContactCategory[]>([]);
  const [allGroups, setAllGroups] = React.useState<ContactGroup[]>([]);
  const [contactGroups, setContactGroups] = React.useState<{ id: number; name: string }[]>([]);
  const [groupToAdd, setGroupToAdd] = React.useState<string>("");
  const [relationships, setRelationships] = React.useState<ContactRelationship[]>([]);
  const [changeLog, setChangeLog] = React.useState<ContactChangeLogEntry[]>([]);
  const [changeSource, setChangeSource] = React.useState<ChangeSource>("manual_edit");
  const [changeNote, setChangeNote] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const [photoUrl, setPhotoUrl] = React.useState<string | null>(null);
  const [photo, setPhoto] = React.useState<ContactPhotoData | null>(null);
  const [isPhotoPreviewOpen, setIsPhotoPreviewOpen] = React.useState(false);
  const photoPreviewCloseRef = React.useRef<HTMLButtonElement | null>(null);
  const [isUploadingPhoto, setIsUploadingPhoto] = React.useState(false);
  const photoInputRef = React.useRef<HTMLInputElement | null>(null);

  const [relQuery, setRelQuery] = React.useState("");
  const [relResults, setRelResults] = React.useState<ContactListItem[]>([]);
  const [relTargetId, setRelTargetId] = React.useState<number | null>(null);
  const [relType, setRelType] = React.useState("");
  const [relNote, setRelNote] = React.useState("");
  const [relStartDate, setRelStartDate] = React.useState("");
  const [relEndDate, setRelEndDate] = React.useState("");
  const [editingRelId, setEditingRelId] = React.useState<number | null>(null);
  const [editRelType, setEditRelType] = React.useState("");
  const [editRelNote, setEditRelNote] = React.useState("");
  const [editRelStartDate, setEditRelStartDate] = React.useState("");
  const [editRelEndDate, setEditRelEndDate] = React.useState("");

  const [organizations, setOrganizations] = React.useState<ContactOrganization[]>([]);
  const [addresses, setAddresses] = React.useState<ContactAddress[]>([]);
  const [addressForm, setAddressForm] = React.useState(emptyAddressForm);
  const [addressText, setAddressText] = React.useState("");
  const [addressParseBusy, setAddressParseBusy] = React.useState(false);
  const [showAddressForm, setShowAddressForm] = React.useState(false);
  const [addressMode, setAddressMode] = React.useState<"new" | "existing">("new");
  const [addressQuery, setAddressQuery] = React.useState("");
  const [addressResults, setAddressResults] = React.useState<AddressSearchResult[]>([]);
  const [addressBusy, setAddressBusy] = React.useState(false);
  const [openAddressMaps, setOpenAddressMaps] = React.useState<Set<number>>(() => new Set());
  const [orgForm, setOrgForm] = React.useState(emptyOrgForm);
  const [showOrgForm, setShowOrgForm] = React.useState(false);
  const [lookupResults, setLookupResults] = React.useState<ContactLookupResult[]>([]);
  const [lookupForm, setLookupForm] = React.useState(emptyLookupForm);
  const [showLookupForm, setShowLookupForm] = React.useState(false);
  const [links, setLinks] = React.useState<ContactLink[]>([]);
  const [linkForm, setLinkForm] = React.useState(emptyLinkForm);
  const [showLinkForm, setShowLinkForm] = React.useState(false);
  const [whatsappProfile, setWhatsappProfile] = React.useState<WhatsappProfile | null>(null);
  const [langForm, setLangForm] = React.useState<{ language: string; native: boolean; level: CefrLevel | "" }>({
    language: "", native: false, level: "",
  });
  const [nationalityInput, setNationalityInput] = React.useState("");

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

  const formFromContact = (c: ContactDetail) => ({
    category_id: String(c.category_id),
    first_name: c.first_name ?? "",
    last_name: c.last_name ?? "",
    gender: c.gender ?? ("" as const),
    display_label: c.display_label ?? "",
    phone_numbers: c.phone_numbers ?? (c.phone_number ? [{ value: c.phone_number, label: null }] : []),
    email_addresses: c.email_addresses ?? (c.email ? [{ value: c.email, label: null }] : []),
    company: c.company ?? "",
    position: c.position ?? "",
    current_city: c.current_city ?? "",
    hometown: c.hometown ?? "",
    birthday: c.birthday ?? "",
    birthday_month: c.birthday_month != null ? String(c.birthday_month) : "",
    birthday_day: c.birthday_day != null ? String(c.birthday_day) : "",
    pesel: c.pesel ?? "",
    notes: c.notes ?? "",
    languages: c.languages ?? [],
    nationality: c.nationality ?? [],
  });

  const loadContact = async () => {
    if (!id || isNew) return;
    setIsLoading(true);
    setMessage("");
    setIsError(false);
    try {
      const response = await axios.get(`${apiUrl}/contacts/${id}`, { headers });
      const fetched: ContactDetail = response.data.contact;
      setContact(fetched);
      setForm(formFromContact(fetched));
      setRelationships(fetched.relationships ?? []);
      setOrganizations(fetched.organizations ?? []);
      setLookupResults(fetched.lookup_results ?? []);
      setAddresses(fetched.addresses ?? []);
      setLinks(fetched.links ?? []);
      setChangeLog(fetched.change_log ?? []);
      setContactGroups(fetched.groups ?? []);
      setWhatsappProfile(fetched.whatsapp_profile ?? null);
      setPhotoUrl(fetched.photo_url ?? null);
      setPhoto(fetched.photo ?? null);
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
    setMode(isNew ? "edit" : "view");
    setContact(null);
    setForm(emptyForm);
    setRelationships([]);
    setOrganizations([]);
    setAddresses([]);
    setAddressForm(emptyAddressForm);
    setShowAddressForm(false);
    setAddressMode("new");
    setAddressQuery("");
    setAddressResults([]);
    setLinks([]);
    setChangeLog([]);
    setContactGroups([]);
    setWhatsappProfile(null);
    setPhotoUrl(null);
    setPhoto(null);
    loadContact();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  React.useEffect(() => {
    setIsPhotoPreviewOpen(false);
  }, [id, photoUrl]);

  React.useEffect(() => {
    if (!isPhotoPreviewOpen || !photoUrl) return;
    const previousFocus = document.activeElement;
    photoPreviewCloseRef.current?.focus();
    const handlePreviewKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setIsPhotoPreviewOpen(false);
      } else if (event.key === "Tab") {
        event.preventDefault();
        photoPreviewCloseRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handlePreviewKeyDown);
    return () => {
      document.removeEventListener("keydown", handlePreviewKeyDown);
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [isPhotoPreviewOpen, photoUrl]);

  const cancelEdit = () => {
    if (contact) {
      setForm(formFromContact(contact));
    }
    setMode("view");
  };

  const handlePhotoSelected = async (file: File) => {
    if (!id || isNew) return;
    setIsUploadingPhoto(true);
    setIsError(false);
    setMessage("");
    try {
      const data = new FormData();
      data.append("photo", file);
      const response = await axios.post(`${apiUrl}/contacts/${id}/photo`, data, {
        headers: { "x-api-key": `${apiKey}` },
      });
      setPhotoUrl(response.data.photo_url ?? null);
      setPhoto(response.data.photo ?? null);
      setMessage("Zapisano zdjęcie.");
    } catch (error: any) {
      console.error("Error uploading contact photo", error);
      setIsError(true);
      setMessage(`Nie udało się zapisać zdjęcia: ${error.response?.data?.message || error.message}`);
    }
    setIsUploadingPhoto(false);
  };

  const handlePhotoRemove = async () => {
    if (!id || isNew) return;
    setIsUploadingPhoto(true);
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/contacts/${id}/photo`, { headers });
      setPhotoUrl(null);
      setPhoto(null);
      setMessage("Usunięto zdjęcie.");
    } catch (error: any) {
      console.error("Error removing contact photo", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć zdjęcia: ${error.response?.data?.message || error.message}`);
    }
    setIsUploadingPhoto(false);
  };

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
    if (![form.first_name, form.last_name, form.display_label].some((value) => value.trim())) {
      setIsError(true);
      setMessage("Podaj imię, nazwisko lub nazwę roboczą.");
      return;
    }
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    const payload = {
      ...form,
      category_id: form.category_id ? Number(form.category_id) : undefined,
      gender: form.gender || null,
      birthday: form.birthday || null,
      birthday_month: form.birthday_month ? Number(form.birthday_month) : null,
      birthday_day: form.birthday_day ? Number(form.birthday_day) : null,
      change_source: changeSource,
      change_note: changeNote.trim() || undefined,
    };
    try {
      if (isNew) {
        const response = await axios.post(`${apiUrl}/contacts`, payload, { headers });
        setMessage("Zapisano kontakt.");
        navigate(`/contacts/${response.data.contact.id}${listContext ? `?list=${encodeURIComponent(listContext)}` : ""}`, { replace: true });
      } else {
        await axios.patch(`${apiUrl}/contacts/${id}`, payload, { headers });
        setMessage("Zapisano zmiany.");
        setChangeSource("manual_edit");
        setChangeNote("");
        await loadContact();
        setMode("view");
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
      navigate(backToListUrl);
    } catch (error: any) {
      console.error("Error deleting contact", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  const toggleArchive = async () => {
    if (!contact || isNew) return;
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/contacts/${id}`, { is_archived: !contact.is_archived }, { headers });
      setMessage(contact.is_archived ? "Przywrócono kontakt z archiwum." : "Zarchiwizowano kontakt.");
      await loadContact();
    } catch (error: any) {
      console.error("Error toggling contact archive status", error);
      setIsError(true);
      setMessage(`Nie udało się zmienić statusu archiwizacji: ${error.response?.data?.message || error.message}`);
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
        start_date: relStartDate || undefined, end_date: relEndDate || undefined,
      }, { headers });
      setRelType("");
      setRelNote("");
      setRelStartDate("");
      setRelEndDate("");
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

  const startEditRelationship = (r: ContactRelationship) => {
    setEditingRelId(r.id);
    setEditRelType(r.relationship_type);
    setEditRelNote(r.note ?? "");
    setEditRelStartDate(r.start_date ?? "");
    setEditRelEndDate(r.end_date ?? "");
  };

  const saveEditRelationship = async () => {
    if (editingRelId === null || !editRelType.trim()) {
      setIsError(true);
      setMessage("Podaj typ powiązania.");
      return;
    }
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/contact_relationships/${editingRelId}`, {
        relationship_type: editRelType.trim(), note: editRelNote.trim() || null,
        start_date: editRelStartDate || null, end_date: editRelEndDate || null,
      }, { headers });
      setEditingRelId(null);
      loadContact();
    } catch (error: any) {
      console.error("Error updating relationship", error);
      setIsError(true);
      setMessage(`Nie udało się zapisać powiązania: ${error.response?.data?.message || error.message}`);
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
        correspondence_address: orgForm.correspondence_address.trim() || undefined,
        website: orgForm.website.trim() || undefined,
        is_primary: orgForm.is_primary,
        is_current: orgForm.is_current,
        status: orgForm.status,
        source_url: orgForm.source_url.trim() || undefined,
        notes: orgForm.notes.trim() || undefined,
        suspended_at: orgForm.suspended_at || undefined,
        verified_at: orgForm.verified_at || undefined,
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

  const addLookupResult = async () => {
    setIsError(false);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/contacts/${id}/lookup_results`, {
        lookup_type: lookupForm.lookup_type,
        status: lookupForm.status,
        url: lookupForm.url.trim() || undefined,
        query_used: lookupForm.query_used.trim() || undefined,
        notes: lookupForm.notes.trim() || undefined,
      }, { headers });
      setLookupForm(emptyLookupForm);
      setShowLookupForm(false);
      loadContact();
    } catch (error: any) {
      console.error("Error adding lookup result", error);
      setIsError(true);
      setMessage(`Nie udało się dodać wyniku wyszukiwania: ${error.response?.data?.message || error.message}`);
    }
  };

  const updateLookupResultStatus = async (lookupResultId: number, status: LookupStatus) => {
    setIsError(false);
    setMessage("");
    try {
      await axios.patch(`${apiUrl}/contact_lookup_results/${lookupResultId}`, { status }, { headers });
      loadContact();
    } catch (error: any) {
      console.error("Error updating lookup result", error);
      setIsError(true);
      setMessage(`Nie udało się zaktualizować wyniku wyszukiwania: ${error.response?.data?.message || error.message}`);
    }
  };

  const removeLookupResult = async (lookupResultId: number) => {
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/contact_lookup_results/${lookupResultId}`, { headers });
      loadContact();
    } catch (error: any) {
      console.error("Error deleting lookup result", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć wyniku wyszukiwania: ${error.response?.data?.message || error.message}`);
    }
  };

  const refreshAddresses = async () => {
    const response = await axios.get(`${apiUrl}/contacts/${id}/addresses`, { headers });
    setAddresses(response.data.addresses ?? []);
    // Preserve unsaved scalar fields while refreshing the audit trail.
    const detail = await axios.get(`${apiUrl}/contacts/${id}`, { headers });
    setChangeLog(detail.data.contact.change_log ?? []);
  };

  React.useEffect(() => {
    setAddressResults([]);
    if (!showAddressForm || addressMode !== "existing" || !addressQuery.trim()) return;
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const response = await axios.get(`${apiUrl}/addresses`, {
          params: { q: addressQuery.trim() },
          headers: { "x-api-key": `${apiKey}` },
        });
        if (active) setAddressResults(response.data.addresses ?? []);
      } catch {
        if (active) { setIsError(true); setMessage("Nie udało się wyszukać adresów."); }
      }
    }, 300);
    return () => { active = false; window.clearTimeout(timer); };
  }, [addressQuery, addressMode, showAddressForm, apiUrl, apiKey, id]);

  const parseAddress = async (text = addressText) => {
    setAddressParseBusy(true);
    setIsError(false); setMessage("");
    try {
      const response = await axios.post<ParsedAddress>(`${apiUrl}/addresses/parse`, { text }, { headers });
      setAddressForm(current => {
        const next = { ...current };
        for (const { key } of addressFields) {
          const value = response.data[key];
          if (value != null) next[key] = value;
        }
        if (response.data.notes != null) next.notes = response.data.notes;
        return next;
      });
      setMessage(addressFields.some(({ key }) => response.data[key] != null) || response.data.notes != null
        ? "Sprawdź i popraw pola przed zapisaniem adresu."
        : "Nie udało się podzielić adresu. Uzupełnij pola ręcznie.");
    } catch (error: any) {
      setIsError(true);
      setMessage(`Nie udało się podzielić adresu. Możesz wpisać pola ręcznie: ${error.response?.data?.message || error.message}`);
    } finally { setAddressParseBusy(false); }
  };

  const addAddress = async (addressId?: number) => {
    setAddressBusy(true);
    setIsError(false);
    setMessage("");
    try {
      const values = { role: addressForm.role.trim() || null, is_primary: addressForm.is_primary };
      await axios.post(`${apiUrl}/contacts/${id}/addresses`, addressId
        ? { ...values, address_id: addressId }
        : { ...values, label: addressForm.label.trim() || null,
          notes: addressForm.notes.trim() || null,
          ...Object.fromEntries(addressFields.map(({ key }) => [key, addressForm[key].trim() || null])) }, { headers });
      setAddressForm(emptyAddressForm);
      setAddressText("");
      setShowAddressForm(false);
      setAddressQuery("");
      await refreshAddresses();
    } catch (error: any) {
      setIsError(true); setMessage(`Nie udało się dodać adresu: ${error.response?.data?.message || error.message}`);
    } finally { setAddressBusy(false); }
  };

  const updateAddressNotes = async (addressId: number, notes: string | null) => {
    setAddressBusy(true);
    setIsError(false); setMessage("");
    try {
      await axios.patch(`${apiUrl}/address/${addressId}`, { notes }, { headers });
      await refreshAddresses();
    } catch (error: any) {
      setIsError(true); setMessage(`Nie udało się zapisać notatek: ${error.response?.data?.message || error.message}`);
    } finally { setAddressBusy(false); }
  };

  const updateAddressLink = async (linkId: number, values: { role?: string | null; is_primary?: boolean }) => {
    setAddressBusy(true);
    setIsError(false); setMessage("");
    try {
      await axios.patch(`${apiUrl}/contact_addresses/${linkId}`, values, { headers });
      await refreshAddresses();
    } catch (error: any) {
      setIsError(true); setMessage(`Nie udało się zmienić adresu: ${error.response?.data?.message || error.message}`);
    } finally { setAddressBusy(false); }
  };

  const geocodeAddress = async (addressId: number) => {
    setAddressBusy(true);
    setIsError(false); setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/address/${addressId}/geocode`, {}, { headers });
      await refreshAddresses();
      if (response.data.resolved === false) {
        setIsError(true); setMessage("Nie znaleziono współrzędnych dla tego adresu.");
      }
    } catch (error: any) {
      setIsError(true); setMessage(`Nie udało się geokodować adresu: ${error.response?.data?.message || error.message}`);
    } finally { setAddressBusy(false); }
  };

  const validateAddress = async (addressId: number) => {
    setAddressBusy(true);
    setIsError(false); setMessage("");
    try {
      const response = await axios.post<AddressValidationResult>(`${apiUrl}/address/${addressId}/validate`, {}, { headers });
      const result = response.data;
      await refreshAddresses();
      if (result.outcome === "confirmed") {
        if (result.postal_code_matches === false) {
          setIsError(true);
          setMessage(`⚠️ Adres istnieje, ale oficjalny kod pocztowy to ${result.official_postal_code} (masz zapisany ${result.address.postal_code}).`);
        } else {
          setMessage("✅ Adres potwierdzony w rejestrze.");
        }
      } else if (result.outcome === "not_found") {
        setIsError(true);
        setMessage("⚠️ Nie znaleziono takiego adresu w rejestrze — sprawdź numer budynku.");
      } else {
        setIsError(true);
        setMessage("❓ Nie udało się zweryfikować adresu (usługa niedostępna lub brak jednoznacznego wyniku) — spróbuj później.");
      }
      const osm = result.osm_supplement;
      if ((result.outcome === "not_found" || result.outcome === "unavailable") && osm) {
        const hints: string[] = [];
        if (osm.found) {
          let hint = "📍 Znaleziono w OpenStreetMap (dane społecznościowe, mniej pewne niż rejestr oficjalny)";
          if (osm.postal_code) hint += ` — sugerowany kod pocztowy: ${osm.postal_code}`;
          if (osm.housename) hint += ` — oznaczenie: ${osm.housename}`;
          hints.push(hint);
        }
        if (!osm.postal_code && osm.nearby_postal_code) {
          hints.push(`📍 OpenStreetMap (dane społecznościowe): kod pocztowy pobliskich budynków przy tej samej ulicy: ${osm.nearby_postal_code} (do potwierdzenia; mniej pewne niż dopasowanie budynku i rejestr oficjalny).`);
        }
        if (hints.length) setMessage(current => `${current}\n${hints.join("\n")}`);
      }
    } catch {
      setIsError(true);
      setMessage("❓ Nie udało się zweryfikować lub odświeżyć adresu — spróbuj później.");
    } finally { setAddressBusy(false); }
  };

  const toggleAddressMap = (linkId: number) => {
    setOpenAddressMaps(current => {
      const next = new Set(current);
      if (next.has(linkId)) next.delete(linkId);
      else next.add(linkId);
      return next;
    });
  };

  const removeAddressLink = async (linkId: number) => {
    setAddressBusy(true);
    setIsError(false); setMessage("");
    try {
      await axios.delete(`${apiUrl}/contact_addresses/${linkId}`, { headers });
      await refreshAddresses();
    } catch (error: any) {
      setIsError(true); setMessage(`Nie udało się usunąć adresu: ${error.response?.data?.message || error.message}`);
    } finally { setAddressBusy(false); }
  };

  const copyOrgAddressToHome = async (address: string) => {
    setAddressMode("new");
    setShowAddressForm(true);
    setAddressText(address);
    setAddressForm({ ...emptyAddressForm, is_primary: addresses.length === 0 });
    await parseAddress(address);
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

  const refreshOrganizationFromCeidg = async (nip: string) => {
    setIsError(false);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/contacts/${id}/organizations/ceidg_lookup`, { nip }, { headers });
      setMessage("Odświeżono dane organizacji z CEIDG.");
      loadContact();
    } catch (error: any) {
      console.error("Error refreshing organization from CEIDG", error);
      setIsError(true);
      setMessage(`Nie udało się odświeżyć z CEIDG: ${error.response?.data?.message || error.message}`);
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

  const addLink = async () => {
    if (!linkForm.url.trim()) {
      setIsError(true);
      setMessage("Podaj adres URL.");
      return;
    }
    setIsError(false);
    setMessage("");
    try {
      await axios.post(`${apiUrl}/contacts/${id}/links`, {
        link_type: linkForm.link_type,
        url: linkForm.url.trim(),
        label: linkForm.label.trim() || undefined,
      }, { headers });
      setLinkForm(emptyLinkForm);
      setShowLinkForm(false);
      loadContact();
    } catch (error: any) {
      console.error("Error adding link", error);
      setIsError(true);
      setMessage(`Nie udało się dodać linku: ${error.response?.data?.message || error.message}`);
    }
  };

  const removeLink = async (linkId: number) => {
    setIsError(false);
    setMessage("");
    try {
      await axios.delete(`${apiUrl}/contact_links/${linkId}`, { headers });
      loadContact();
    } catch (error: any) {
      console.error("Error deleting link", error);
      setIsError(true);
      setMessage(`Nie udało się usunąć linku: ${error.response?.data?.message || error.message}`);
    }
  };

  const addLanguage = () => {
    const language = langForm.language.trim();
    if (!language) return;
    const entry: ContactLanguage = {
      language, native: langForm.native, level: langForm.native ? null : (langForm.level || null),
    };
    setForm({ ...form, languages: [...form.languages, entry] });
    setLangForm({ language: "", native: false, level: "" });
  };

  const removeLanguage = (index: number) => {
    setForm({ ...form, languages: form.languages.filter((_, i) => i !== index) });
  };

  const addNationality = () => {
    const value = nationalityInput.trim();
    if (!value || form.nationality.includes(value)) return;
    setForm({ ...form, nationality: [...form.nationality, value] });
    setNationalityInput("");
  };

  const removeNationality = (index: number) => {
    setForm({ ...form, nationality: form.nationality.filter((_, i) => i !== index) });
  };

  const inputStyle: React.CSSProperties = { padding: "6px 10px", width: "100%", boxSizing: "border-box" };
  const addressSection = !isNew && (
    <section>
      <h3>Adresy</h3>
      {addresses.length === 0 && <p style={{ color: "#667" }}>Brak zapisanych adresów.</p>}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {addresses.map((link) => (
          <li key={link.id} style={{ marginBottom: 10, padding: 10, border: "1px solid #ddd", borderRadius: 6 }}>
            <div>{link.is_primary && "⭐ "}{link.address.label && <strong>{link.address.label}: </strong>}
              {link.role && <span>{link.role} — </span>}{link.address.formatted_address}</div>
            {link.address.notes && <div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>📝 Notatki: {link.address.notes}</div>}
            {link.address.verified_at && <div style={{ marginTop: 4, color: "#667" }}>
              <small>Zweryfikowano: {new Date(link.address.verified_at).toLocaleDateString("pl-PL")}</small>
            </div>}
            {mode === "edit" && <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6, flexWrap: "wrap" }}>
              <label style={{ width: "100%" }}>Notatki (kod domofonu, dojazd...)
                <textarea key={`${link.id}-${link.address.notes}`} defaultValue={link.address.notes ?? ""}
                  maxLength={ADDRESS_NOTES_MAX_LENGTH} rows={3} style={inputStyle} disabled={addressBusy}
                  onBlur={(event) => {
                    const notes = event.target.value.trim() || null;
                    if (notes !== link.address.notes) void updateAddressNotes(link.address.id, notes);
                  }} />
                <small>Wspólne dla wszystkich kontaktów używających tego adresu. Zapis po opuszczeniu pola.</small>
              </label>
              <label>Rola <input key={`${link.id}-${link.role}`} defaultValue={link.role ?? ""} maxLength={50}
                disabled={addressBusy} onBlur={(event) => {
                  const role = event.target.value.trim() || null;
                  if (role !== link.role) void updateAddressLink(link.id, { role });
                }} /></label>
              <label><input type="checkbox" checked={link.is_primary} disabled={addressBusy}
                onChange={(event) => void updateAddressLink(link.id, { is_primary: event.target.checked })} /> Główny adres</label>
              <button className={"button"} type="button" disabled={addressBusy}
                onClick={() => void removeAddressLink(link.id)}>Usuń</button>
              {link.address.latitude == null && <button className={"button"} type="button" disabled={addressBusy}
                onClick={() => void geocodeAddress(link.address.id)}>📍 Geokoduj</button>}
              <button className={"button"} type="button" disabled={addressBusy}
                onClick={() => void validateAddress(link.address.id)}>✓ Zweryfikuj adres</button>
            </div>}
            {link.address.latitude != null && link.address.longitude != null && <>
              <button className={"button"} type="button" style={{ marginTop: 6 }} aria-expanded={openAddressMaps.has(link.id)}
                onClick={() => toggleAddressMap(link.id)}>
                {openAddressMaps.has(link.id) ? "🗺 Ukryj mapę" : "🗺 Pokaż na mapie"}
              </button>
              <a
                href={`https://www.google.com/maps/dir/?api=1&destination=${link.address.latitude},${link.address.longitude}`}
                target="_blank" rel="noopener noreferrer"
                className={"button"} style={{ marginTop: 6, marginLeft: 6, display: "inline-block", textDecoration: "none" }}
              >
                🧭 Otwórz w Google Maps (trasa)
              </a>
              {openAddressMaps.has(link.id) && <React.Suspense fallback={<p>Ładowanie mapy…</p>}>
                <CountryMap countries={[]} places={[{
                  name: link.address.label || link.address.formatted_address,
                  lat: link.address.latitude,
                  lon: link.address.longitude,
                }]} />
              </React.Suspense>}
            </>}
          </li>
        ))}
      </ul>
      {mode === "edit" && <>
        <button className={"button"} type="button" onClick={() => setShowAddressForm(!showAddressForm)}>
          {showAddressForm ? "Anuluj" : "+ Dodaj adres"}
        </button>
        {showAddressForm && <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
          <div style={{ display: "flex", gap: 12 }}>
            <label><input type="radio" name="addressMode" checked={addressMode === "new"}
              onChange={() => setAddressMode("new")} /> Nowy adres</label>
            <label><input type="radio" name="addressMode" checked={addressMode === "existing"}
              onChange={() => setAddressMode("existing")} /> Istniejący adres</label>
          </div>
          <label>Rola<input value={addressForm.role} maxLength={50} style={inputStyle}
            onChange={(event) => setAddressForm({ ...addressForm, role: event.target.value })} /></label>
          <label><input type="checkbox" checked={addressForm.is_primary}
            onChange={(event) => setAddressForm({ ...addressForm, is_primary: event.target.checked })} /> Główny adres</label>
          {addressMode === "new" ? <>
            <label>Etykieta<input value={addressForm.label} maxLength={100} style={inputStyle}
              onChange={(event) => setAddressForm({ ...addressForm, label: event.target.value })} /></label>
            <label>Wklej adres<textarea value={addressText} style={inputStyle} rows={2}
              placeholder="Wklej pełny adres, np. z e-maila lub wizytówki"
              onChange={(event) => setAddressText(event.target.value)} /></label>
            <button className={"button"} type="button" disabled={addressParseBusy || addressBusy || !addressText.trim()}
              onClick={() => void parseAddress()}>{addressParseBusy ? "Dzielenie adresu…" : "Podziel adres"}</button>
            {addressFields.map(({ key, label, maxLength }) => <label key={key}>{label}
              <input value={addressForm[key]} maxLength={maxLength} style={inputStyle}
                placeholder={key === "postal_code" ? "np. 95-054" : undefined}
                aria-describedby={key === "postal_code" ? "address-postal-hint" : undefined}
                onChange={(event) => setAddressForm(current => ({ ...current, [key]: event.target.value }))} />
              {key === "postal_code" && <small id="address-postal-hint">Format: NN-NNN</small>}
            </label>)}
            <label>Notatki (kod domofonu, dojazd...)
              <textarea value={addressForm.notes} maxLength={ADDRESS_NOTES_MAX_LENGTH} rows={3} style={inputStyle}
                onChange={(event) => setAddressForm(current => ({ ...current, notes: event.target.value }))} />
            </label>
            <button className={"button"} type="button" disabled={addressBusy || addressParseBusy}
              onClick={() => void addAddress()}>Zapisz adres</button>
          </> : <>
            <label>Szukaj adresu<input value={addressQuery} style={inputStyle}
              onChange={(event) => setAddressQuery(event.target.value)} /></label>
            {addressResults.map((address) => <div key={address.id} style={{ padding: 8, border: "1px solid #ddd", borderRadius: 6 }}>
              <div>{address.label && <strong>{address.label}: </strong>}{address.formatted_address}</div>
              {address.linked_contacts.length > 0 && <div style={{ color: "#667", fontSize: "0.85em" }}>
                Używany przez: {address.linked_contacts.map((person) => person.display_name).join(", ")}
              </div>}
              <button className={"button"} type="button" disabled={addressBusy}
                onClick={() => void addAddress(address.id)}>Wybierz adres</button>
            </div>)}
          </>}
        </div>}
      </>}
    </section>
  );
  const outgoing = relationships.filter((r) => r.direction === "outgoing");
  const incoming = relationships.filter((r) => r.direction === "incoming");
  const isCompanyCategory = categories.find((c) => String(c.id) === form.category_id)?.name === "Firma";

  return (
    <div style={{ maxWidth: 560 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <h2 style={{ margin: 0 }}>{isNew ? "Nowy kontakt" : "Kontakt"}</h2>
          {contact?.is_archived && (
            <span style={{ fontSize: "0.8em", color: "#a33", border: "1px solid #e3a", borderRadius: 4, padding: "2px 8px" }}>
              archiwalny
            </span>
          )}
        </div>
        {!isNew && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className={"button"} type="button" onClick={() => navigate(backToListUrl)}>
              ← Wróć do listy
            </button>
            <button className={"button"} type="button" disabled={isLoading} onClick={toggleArchive}>
              {contact?.is_archived ? "↺ Przywróć z archiwum" : "🗄 Archiwizuj"}
            </button>
            <button className={"button"} type="button" onClick={() => (mode === "view" ? setMode("edit") : cancelEdit())}>
              {mode === "view" ? "✏️ Edytuj" : "← Podgląd"}
            </button>
          </div>
        )}
      </div>

      {isLoading && <div className={"loader"}></div>}
      {searchParams.get("merged") === "1" && <p role="status" style={{ color: "#16803a" }}>Scalono kontakty.</p>}
      {message && (
        <p className={isError ? "errorText" : undefined} style={{ whiteSpace: "pre-line", color: isError ? undefined : "#2e7d43" }}>
          {message}
        </p>
      )}

      {!isNew && (
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start", marginBottom: 14 }}>
          <div
            style={{
              width: 100, height: 100, borderRadius: 8, background: "#eef1f5", border: "1px solid #d5dde8",
              display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden", flexShrink: 0,
            }}
          >
            {photoUrl ? (
              <button
                type="button"
                aria-label="Powiększ zdjęcie kontaktu"
                aria-haspopup="dialog"
                onClick={(event) => {
                  event.stopPropagation();
                  setIsPhotoPreviewOpen(true);
                }}
                onMouseEnter={(event) => { event.currentTarget.style.opacity = "0.85"; }}
                onMouseLeave={(event) => { event.currentTarget.style.opacity = "1"; }}
                style={{ width: "100%", height: "100%", padding: 0, border: "none", background: "none", cursor: "pointer", transition: "opacity 150ms ease" }}
              >
                <img src={photoUrl} alt="Zdjęcie kontaktu" style={{ display: "block", width: "100%", height: "100%", objectFit: "contain" }} />
              </button>
            ) : (
              <span style={{ color: "#98a2b3", fontSize: "0.75em", textAlign: "center", padding: 4 }}>Brak zdjęcia</span>
            )}
          </div>
          {mode === "edit" && (
            <div>
              <input
                ref={photoInputRef}
                type="file"
                accept="image/*"
                style={{ display: "none" }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handlePhotoSelected(file);
                  e.target.value = "";
                }}
              />
              <button className={"button"} type="button" disabled={isUploadingPhoto} onClick={() => photoInputRef.current?.click()}>
                {isUploadingPhoto ? "Wysyłanie..." : photoUrl ? "Zmień zdjęcie" : "Dodaj zdjęcie"}
              </button>
              {photoUrl && (
                <button
                  className={"button"}
                  type="button"
                  disabled={isUploadingPhoto}
                  style={{ marginLeft: 6 }}
                  onClick={handlePhotoRemove}
                >
                  Usuń zdjęcie
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {!isNew && id && photo && <ContactPhotoDescriptions key={`${id}:${photo.storage_key}`}
        photo={photo} contactId={id} apiUrl={apiUrl} apiKey={`${apiKey}`} onChange={setPhoto} />}
      {!isNew && id && <ContactPhotoHistory key={id} contactId={id} apiUrl={apiUrl} apiKey={`${apiKey}`}
        onRestored={(url, updatedPhoto) => { setPhotoUrl(url); setPhoto(updatedPhoto); }} />}
      {!isNew && id && photo && contact && <ContactFamilyForm key={`family:${id}:${photo.storage_key}`}
        photo={photo} contactId={id} contactName={otherName(contact)} apiUrl={apiUrl} apiKey={`${apiKey}`}
        groups={allGroups} onCreated={() => { void loadContact(); }} />}
      {isPhotoPreviewOpen && photoUrl && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Podgląd zdjęcia kontaktu"
          onClick={(event) => {
            event.stopPropagation();
            setIsPhotoPreviewOpen(false);
          }}
          style={{ position: "fixed", inset: 0, zIndex: 10000, background: "rgba(0, 0, 0, 0.8)", display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <img
            src={photoUrl}
            alt="Zdjęcie kontaktu"
            onClick={(event) => event.stopPropagation()}
            style={{ maxWidth: "90vw", maxHeight: "90vh", objectFit: "contain" }}
          />
          <button
            ref={photoPreviewCloseRef}
            type="button"
            aria-label="Zamknij podgląd zdjęcia"
            onClick={(event) => {
              event.stopPropagation();
              setIsPhotoPreviewOpen(false);
            }}
            style={{ position: "absolute", top: 16, right: 16, width: 44, height: 44, border: "none", borderRadius: 8, background: "rgba(0, 0, 0, 0.6)", color: "#fff", fontSize: 24, cursor: "pointer" }}
          >
            ✕
          </button>
        </div>
      )}

      {mode === "view" && contact ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {contact.category_name && <div style={{ color: "#667" }}>{contact.category_name}</div>}
          <div style={{ fontSize: "1.2em", fontWeight: 600 }}>
            {otherName(contact)}
          </div>
          {contact.category_name !== "Firma" && contact.gender && <div><strong>Płeć:</strong> {GENDER_LABELS[contact.gender]}</div>}
          {(contact.phone_numbers ?? (contact.phone_number ? [{ value: contact.phone_number, label: null }] : [])).map((entry, index) => (
            <div key={`phone-${index}`}><strong>Telefon{index === 0 ? " główny" : ""}:</strong> {entry.value}{entry.label && ` (${entry.label})`}</div>
          ))}
          {(contact.email_addresses ?? (contact.email ? [{ value: contact.email, label: null }] : [])).map((entry, index) => (
            <div key={`email-${index}`}><strong>Email{index === 0 ? " główny" : ""}:</strong> {entry.value}{entry.label && ` (${entry.label})`}</div>
          ))}
          {contact.company && <div><strong>Firma:</strong> {contact.company}</div>}
          {contact.category_name !== "Firma" && contact.position && <div><strong>Stanowisko:</strong> {contact.position}</div>}
          {addressSection}
          {contact.category_name !== "Firma" && contact.current_city && <div><strong>Mieszka w:</strong> {contact.current_city}</div>}
          {contact.category_name !== "Firma" && contact.hometown && <div><strong>Pochodzi z:</strong> {contact.hometown}</div>}
          {contact.birthday && (
            <div><strong>{contact.category_name === "Firma" ? "Data założenia" : "Urodziny"}:</strong> {contact.birthday}</div>
          )}
          {!contact.birthday && contact.birthday_month && contact.birthday_day && (
            <div><strong>{contact.category_name === "Firma" ? "Data założenia" : "Urodziny"}:</strong> {contact.birthday_day} {MONTHS_GENITIVE[contact.birthday_month - 1]} <span style={{ color: "#667" }}>(bez roku)</span></div>
          )}
          {contact.category_name !== "Firma" && contact.pesel && <div><strong>PESEL:</strong> {contact.pesel}</div>}
          {contact.category_name !== "Firma" && contact.nationality.length > 0 && (
            <div><strong>Narodowość:</strong> {contact.nationality.join(", ")}</div>
          )}
          {contact.category_name !== "Firma" && contact.languages.length > 0 && (
            <div><strong>Języki:</strong> {contact.languages.map(languageSummary).join(", ")}</div>
          )}
          {contact.notes && <div><strong>Notatki:</strong> {linkifyPlainText(contact.notes)}</div>}

          <div style={{ marginTop: 10 }}>
            <div style={{ marginBottom: 4 }}>Grupy</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {contactGroups.length === 0 && <span style={{ color: "#667" }}>Brak grup.</span>}
              {contactGroups.map((g) => (
                <span
                  key={g.id}
                  style={{ fontSize: "0.85em", color: "#0369a1", background: "#e0f2fe", borderRadius: 4, padding: "2px 6px" }}
                >
                  {g.name}
                </span>
              ))}
            </div>
          </div>

        </div>
      ) : (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label>
          Kategoria
          <select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} style={inputStyle}>
            <option value="">(domyślna)</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        {!isCompanyCategory && <label>
          Imię
          <input type="text" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} style={inputStyle} />
        </label>}
        {!isCompanyCategory && <label>
          Nazwisko
          <input type="text" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} style={inputStyle} />
        </label>}
        {!isCompanyCategory && <label>
          Płeć — pomocne przy obcych imionach/nazwiskach, gdy nie widać zdjęcia
          <select value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value as Gender | "" })} style={inputStyle}>
            <option value="">(nie podano)</option>
            {(Object.keys(GENDER_LABELS) as Gender[]).map((g) => (
              <option key={g} value={g}>{GENDER_LABELS[g]}</option>
            ))}
          </select>
        </label>}
        <label>
          Nazwa robocza (gdy nie znasz imienia ani nazwiska)
          <input type="text" maxLength={200} value={form.display_label} onChange={(e) => setForm({ ...form, display_label: e.target.value })} style={inputStyle} />
        </label>
        <ContactChannelsEditor title="Telefony" kind="tel" entries={form.phone_numbers}
          onChange={(phone_numbers) => setForm({ ...form, phone_numbers })} />
        <ContactChannelsEditor title="Adresy e-mail" kind="email" entries={form.email_addresses}
          onChange={(email_addresses) => setForm({ ...form, email_addresses })} />
        <label>
          Firma
          <input type="text" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} style={inputStyle} />
        </label>
        {!isCompanyCategory && <label>
          Stanowisko
          <input type="text" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} style={inputStyle} />
        </label>}
        {addressSection}
        {!isCompanyCategory && <label>
          Mieszka w (miasto) — motyw do small talku
          <input type="text" value={form.current_city} onChange={(e) => setForm({ ...form, current_city: e.target.value })} style={inputStyle} />
        </label>}
        {!isCompanyCategory && <label>
          Pochodzi z (rodzinne miasto) — motyw do small talku
          <input type="text" value={form.hometown} onChange={(e) => setForm({ ...form, hometown: e.target.value })} style={inputStyle} />
        </label>}
        <label>
          {isCompanyCategory ? "Data założenia (jeśli znana z rokiem)" : "Urodziny (jeśli znasz pełną datę, z rokiem)"}
          <input type="date" value={form.birthday} onChange={(e) => setForm({ ...form, birthday: e.target.value })} style={inputStyle} />
        </label>
        <label>
          {isCompanyCategory
            ? "Data założenia bez roku (dzień i miesiąc) — np. gdy rok nie jest pewny"
            : "Urodziny bez roku (dzień i miesiąc) — np. gdy Facebook ukrywa rok"}
          <div style={{ display: "flex", gap: 8 }}>
            <select
              value={form.birthday_day}
              onChange={(e) => setForm({ ...form, birthday_day: e.target.value })}
              style={{ ...inputStyle, width: "auto" }}
            >
              <option value="">dzień</option>
              {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => (
                <option key={day} value={day}>{day}</option>
              ))}
            </select>
            <select
              value={form.birthday_month}
              onChange={(e) => setForm({ ...form, birthday_month: e.target.value })}
              style={{ ...inputStyle, width: "auto" }}
            >
              <option value="">miesiąc</option>
              {MONTHS_GENITIVE.map((name, index) => (
                <option key={name} value={index + 1}>{name}</option>
              ))}
            </select>
          </div>
        </label>
        {!isCompanyCategory && <label>
          PESEL
          <input type="text" inputMode="numeric" maxLength={11} value={form.pesel}
            onChange={(e) => setForm({ ...form, pesel: e.target.value.replace(/[^0-9]/g, "") })} style={inputStyle} />
        </label>}
        {!isCompanyCategory && <div>
          <div style={{ marginBottom: 4 }}>Narodowość</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
            {form.nationality.length === 0 && <span style={{ color: "#667" }}>Brak.</span>}
            {form.nationality.map((value, index) => (
              <span
                key={`${value}-${index}`}
                style={{
                  display: "flex", alignItems: "center", gap: 4, fontSize: "0.85em", color: "#0369a1",
                  background: "#e0f2fe", borderRadius: 4, padding: "2px 6px",
                }}
              >
                {value}
                <button
                  type="button"
                  onClick={() => removeNationality(index)}
                  style={{ border: "none", background: "none", color: "#0369a1", cursor: "pointer", padding: 0, lineHeight: 1 }}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              placeholder="Narodowość (np. polska)"
              value={nationalityInput}
              onChange={(e) => setNationalityInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addNationality(); } }}
              style={{ padding: "4px 8px", flex: 1 }}
            />
            <button className={"button"} type="button" disabled={!nationalityInput.trim()} onClick={addNationality}>
              Dodaj
            </button>
          </div>
        </div>}
        {!isCompanyCategory && <div>
          <div style={{ marginBottom: 4 }}>Języki</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
            {form.languages.length === 0 && <span style={{ color: "#667" }}>Brak języków.</span>}
            {form.languages.map((lang, index) => (
              <span
                key={`${lang.language}-${index}`}
                style={{
                  display: "flex", alignItems: "center", gap: 4, fontSize: "0.85em", color: "#0369a1",
                  background: "#e0f2fe", borderRadius: 4, padding: "2px 6px",
                }}
              >
                {languageSummary(lang)}
                <button
                  type="button"
                  onClick={() => removeLanguage(index)}
                  style={{ border: "none", background: "none", color: "#0369a1", cursor: "pointer", padding: 0, lineHeight: 1 }}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input
              type="text"
              placeholder="Język (np. angielski)"
              value={langForm.language}
              onChange={(e) => setLangForm({ ...langForm, language: e.target.value })}
              style={{ padding: "4px 8px", flex: 1, minWidth: 140 }}
            />
            <label style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <input
                type="checkbox"
                checked={langForm.native}
                onChange={(e) => setLangForm({ ...langForm, native: e.target.checked, level: "" })}
              />
              native speaker
            </label>
            {!langForm.native && (
              <select
                value={langForm.level}
                onChange={(e) => setLangForm({ ...langForm, level: e.target.value as CefrLevel | "" })}
                style={{ padding: "4px 8px" }}
              >
                <option value="">(poziom nieznany)</option>
                {LANGUAGE_LEVELS.map((level) => (
                  <option key={level} value={level}>{level}</option>
                ))}
              </select>
            )}
            <button className={"button"} type="button" disabled={!langForm.language.trim()} onClick={addLanguage}>
              Dodaj
            </button>
          </div>
        </div>}
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

        <div style={{ padding: 8, background: "#f5f7fa", border: "1px solid #d5dde8", borderRadius: 6 }}>
          <div style={{ marginBottom: 6, color: "#667", fontSize: "0.9em" }}>
            Skąd ta zmiana? (zapisywane w historii kontaktu)
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select
              value={changeSource}
              onChange={(e) => setChangeSource(e.target.value as ChangeSource)}
              style={{ padding: "4px 8px" }}
            >
              {(Object.keys(CHANGE_SOURCE_LABELS) as ChangeSource[]).map((s) => (
                <option key={s} value={s}>{CHANGE_SOURCE_LABELS[s]}</option>
              ))}
            </select>
            <input
              type="text"
              value={changeNote}
              placeholder="Notatka (opcjonalnie, np. „telefon podany przez sąsiada”)"
              onChange={(e) => setChangeNote(e.target.value)}
              style={{ padding: "4px 8px", flex: 1, minWidth: 220 }}
            />
          </div>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button className={"button"} type="button" disabled={isLoading} onClick={save}>
            Zapisz
          </button>
          {!isNew && (
            <button className={"button"} type="button" disabled={isLoading} onClick={remove}>
              Usuń
            </button>
          )}
        </div>
      </div>
      )}

      {!isNew && (
        <div style={{ marginTop: 24 }}>
          {!!contact?.events?.length && <section style={{ marginBottom: 24 }}>
            <h3>Wydarzenia</h3>
            {/* Without a whatsapp_profile there's no "Pomysły na rozmowę" section to
                fold this into (see WhatsappProfileView below) — show the same hint
                standalone so it isn't lost for contacts never analysed via WhatsApp. */}
            {!whatsappProfile && (() => {
              const latest = latestEvent(contact.events);
              return latest && (
                <p style={{ background: "#eef6ff", padding: "8px 10px", borderRadius: 6, marginBottom: 8 }}>
                  💬 Pomysł na rozmowę: {eventHintText(latest)}
                </p>
              );
            })()}
            <ul>
              {contact.events.map(event => <li key={event.id}>
                <time dateTime={event.event_date}>{event.event_date}</time>{" — "}
                {event.group_id !== null && <><NavLink to={`/contact_groups/${event.group_id}`}>{event.group_name}</NavLink>{" — "}</>}
                {event.title}
                {event.participants.filter(participant => String(participant.id) !== id).map(participant => (
                  <NavLink key={participant.id} to={`/contacts/${participant.id}`}
                    style={{ display: "inline-block", marginLeft: 6, padding: "2px 8px", borderRadius: 12, background: "#eef2ff" }}>
                    {participant.display_name}
                  </NavLink>
                ))}
              </li>)}
            </ul>
          </section>}
          {!!contact?.chat_conversations?.length && <section style={{ marginBottom: 24 }}>
            <h3>Czaty</h3>
            <ul style={{ listStyle: "none", padding: 0 }}>
              {contact.chat_conversations.map((conv) => (
                <li key={conv.id} style={{ marginBottom: 4 }}>
                  <NavLink to={`/chats/${conv.id}?contact_id=${id}`}>{conv.display_name}</NavLink>
                  {" — "}
                  {conv.message_count.toLocaleString("pl")} wiadomości
                  {conv.last_message_at && <> · ostatnia: {new Date(conv.last_message_at).toLocaleDateString("pl-PL")}</>}
                </li>
              ))}
            </ul>
          </section>}
          {contact?.category_name !== "Firma" && <ContactInterestsEducation key={id} contactId={id!} editable={mode === "edit"} onChanged={() => {
            // Refresh the audit without replacing unsaved fields in the main contact form.
            void axios.get(`${apiUrl}/contacts/${id}`, { headers })
              .then(response => setChangeLog(response.data.contact.change_log ?? []))
              .catch(() => { setIsError(true); setMessage("Nie udało się odświeżyć historii zmian."); });
          }} />}
          {contact?.category_name !== "Firma" && <>
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
                  {org.address && (
                    <div style={{ fontSize: "0.85em", color: "#667", display: "flex", gap: 6, alignItems: "center" }}>
                      <span>Adres rejestrowy: {org.address}</span>
                      {mode === "edit" && org.org_type === "jdg" && (
                        <button
                          type="button"
                          onClick={() => copyOrgAddressToHome(org.address as string)}
                          title="Skopiuj jako adres domowy kontaktu"
                          style={{ border: "none", background: "none", color: "#2b6cb0", cursor: "pointer", padding: 0, fontSize: "0.95em" }}
                        >
                          → adres domowy
                        </button>
                      )}
                    </div>
                  )}
                  {org.correspondence_address && (
                    <div style={{ fontSize: "0.85em", color: "#667", display: "flex", gap: 6, alignItems: "center" }}>
                      <span>Adres do doręczeń: {org.correspondence_address}</span>
                      {mode === "edit" && org.org_type === "jdg" && (
                        <button
                          type="button"
                          onClick={() => copyOrgAddressToHome(org.correspondence_address as string)}
                          title="Skopiuj jako adres domowy kontaktu"
                          style={{ border: "none", background: "none", color: "#2b6cb0", cursor: "pointer", padding: 0, fontSize: "0.95em" }}
                        >
                          → adres domowy
                        </button>
                      )}
                    </div>
                  )}
                  {org.website && (
                    <div style={{ fontSize: "0.85em", color: "#667" }}>
                      Strona WWW:{" "}
                      <a
                        href={/^https?:\/\//i.test(org.website) ? org.website : `https://${org.website}`}
                        target="_blank" rel="noreferrer" style={{ wordBreak: "break-all" }}
                      >
                        {org.website}
                      </a>
                    </div>
                  )}
                  {(org.verified_at || org.suspended_at) && (
                    <div style={{ fontSize: "0.85em", color: "#667" }}>
                      {org.verified_at && <span>Zweryfikowano w rejestrze: {org.verified_at} </span>}
                      {org.suspended_at && <span style={{ color: "#a33" }}>· Zawieszona od: {org.suspended_at}</span>}
                    </div>
                  )}
                  {org.notes && <div style={{ fontSize: "0.85em", color: "#667" }}>{linkifyPlainText(org.notes)}</div>}
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
                    {org.nip && org.org_type === "jdg" && (
                      <button
                        type="button"
                        onClick={() => refreshOrganizationFromCeidg(org.nip as string)}
                        title="Pobierz aktualne dane z oficjalnego API CEIDG i zapisz"
                        style={{ border: "none", background: "none", color: "#2b6cb0", cursor: "pointer", padding: 0 }}
                      >
                        ↻ Odśwież z CEIDG
                      </button>
                    )}
                    {mode === "edit" && org.status === "candidate" && (
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
                    {mode === "edit" && (
                      <button
                        type="button"
                        onClick={() => removeOrganization(org.id)}
                        style={{ border: "none", background: "none", color: "#a33", cursor: "pointer", padding: 0 }}
                      >
                        Usuń
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {mode === "edit" && !showOrgForm && (
            <button className={"button"} type="button" onClick={() => setShowOrgForm(true)}>
              + Dodaj organizację
            </button>
          )}
          {mode === "edit" && showOrgForm && (
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
                <input
                  type="text" placeholder="Adres do doręczeń" value={orgForm.correspondence_address}
                  onChange={(e) => setOrgForm({ ...orgForm, correspondence_address: e.target.value })}
                  style={{ padding: "4px 8px", minWidth: 220 }}
                />
                <input
                  type="text" placeholder="Strona WWW" value={orgForm.website}
                  onChange={(e) => setOrgForm({ ...orgForm, website: e.target.value })}
                  style={{ padding: "4px 8px", minWidth: 160 }}
                />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
                <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  Zweryfikowano w rejestrze:
                  <input
                    type="date" value={orgForm.verified_at}
                    onChange={(e) => setOrgForm({ ...orgForm, verified_at: e.target.value })}
                    style={{ padding: "4px 8px" }}
                  />
                </label>
                <label style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  Data zawieszenia:
                  <input
                    type="date" value={orgForm.suspended_at}
                    onChange={(e) => setOrgForm({ ...orgForm, suspended_at: e.target.value })}
                    style={{ padding: "4px 8px" }}
                  />
                </label>
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
          </>}

          <h3>Wyniki wyszukiwania OSINT</h3>
          <p style={{ color: "#667", fontSize: "0.85em", marginTop: -6 }}>
            Ślad ustaleń z badania OSINT (np. telefon, profil LinkedIn, e-mail znaleziony w publicznym rejestrze) —
            każdy wpis ma status pewności, niezależnie od pól kontaktu ustawianych ręcznie lub z importu.
          </p>
          {lookupResults.length === 0 && (
            <p style={{ color: "#667" }}>Brak zapisanych wyników wyszukiwania.</p>
          )}
          {lookupResults.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {lookupResults.map((lr) => (
                <li
                  key={lr.id}
                  style={{
                    padding: "8px 10px", marginBottom: 6, borderRadius: 6,
                    background: lr.status === "candidate" ? "#fff8e6" : "#f5f7fa",
                    border: `1px solid ${lr.status === "candidate" ? "#e8d18a" : "#d5dde8"}`,
                  }}
                >
                  <div>
                    <strong>{LOOKUP_TYPE_LABELS[lr.lookup_type]}</strong>
                    {lr.url && <span>{" — "}{lr.url}</span>}
                    <span style={{ marginLeft: 8, fontSize: "0.8em", color: "#667" }}>
                      [{LOOKUP_STATUS_LABELS[lr.status]}]
                    </span>
                  </div>
                  {lr.query_used && (
                    <div style={{ fontSize: "0.85em", color: "#667" }}>Zapytanie: {lr.query_used}</div>
                  )}
                  {lr.notes && <div style={{ fontSize: "0.85em", color: "#667" }}>{linkifyPlainText(lr.notes)}</div>}
                  <div style={{ fontSize: "0.8em", color: "#889" }}>Sprawdzono: {lr.searched_at?.slice(0, 10)}</div>
                  <div style={{ marginTop: 4, display: "flex", gap: 8, alignItems: "center" }}>
                    {mode === "edit" && lr.status === "candidate" && (
                      <>
                        <button
                          type="button"
                          onClick={() => updateLookupResultStatus(lr.id, "confirmed")}
                          style={{ border: "none", background: "none", color: "#2e7d43", cursor: "pointer", padding: 0 }}
                        >
                          ✓ Potwierdź
                        </button>
                        <button
                          type="button"
                          onClick={() => updateLookupResultStatus(lr.id, "rejected")}
                          style={{ border: "none", background: "none", color: "#a33", cursor: "pointer", padding: 0 }}
                        >
                          ✕ Odrzuć
                        </button>
                      </>
                    )}
                    {mode === "edit" && (
                      <button
                        type="button"
                        onClick={() => removeLookupResult(lr.id)}
                        style={{ border: "none", background: "none", color: "#a33", cursor: "pointer", padding: 0 }}
                      >
                        Usuń
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {mode === "edit" && !showLookupForm && (
            <button className={"button"} type="button" onClick={() => setShowLookupForm(true)}>
              + Dodaj wynik wyszukiwania
            </button>
          )}
          {mode === "edit" && showLookupForm && (
            <div style={{ marginTop: 8, padding: 8, background: "#f5f7fa", border: "1px solid #d5dde8", borderRadius: 6 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <select
                  value={lookupForm.lookup_type}
                  onChange={(e) => setLookupForm({ ...lookupForm, lookup_type: e.target.value as LookupType })}
                  style={{ padding: "4px 8px" }}
                >
                  {(Object.keys(LOOKUP_TYPE_LABELS) as LookupType[]).map((t) => (
                    <option key={t} value={t}>{LOOKUP_TYPE_LABELS[t]}</option>
                  ))}
                </select>
                <input
                  type="text" placeholder="Odnaleziona wartość (URL / telefon / e-mail)" value={lookupForm.url}
                  onChange={(e) => setLookupForm({ ...lookupForm, url: e.target.value })}
                  style={{ padding: "4px 8px", minWidth: 260 }}
                />
                <select
                  value={lookupForm.status}
                  onChange={(e) => setLookupForm({ ...lookupForm, status: e.target.value as LookupStatus })}
                  style={{ padding: "4px 8px" }}
                >
                  {(Object.keys(LOOKUP_STATUS_LABELS) as LookupStatus[]).map((s) => (
                    <option key={s} value={s}>{LOOKUP_STATUS_LABELS[s]}</option>
                  ))}
                </select>
              </div>
              <input
                type="text" placeholder="Zapytanie użyte do wyszukania" value={lookupForm.query_used}
                onChange={(e) => setLookupForm({ ...lookupForm, query_used: e.target.value })}
                style={{ padding: "4px 8px", marginTop: 6, width: "100%", boxSizing: "border-box" }}
              />
              <textarea
                placeholder="Notatki (źródło, uzasadnienie)" value={lookupForm.notes} rows={2}
                onChange={(e) => setLookupForm({ ...lookupForm, notes: e.target.value })}
                style={{ padding: "4px 8px", marginTop: 6, width: "100%", boxSizing: "border-box" }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                <button className={"button"} type="button" onClick={addLookupResult}>Zapisz wynik</button>
                <button className={"button"} type="button" onClick={() => { setShowLookupForm(false); setLookupForm(emptyLookupForm); }}>
                  Anuluj
                </button>
              </div>
            </div>
          )}

          <h3>Linki</h3>
          {links.length === 0 && (
            <p style={{ color: "#667" }}>Brak zapisanych linków.</p>
          )}
          {links.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {links.map((link) => (
                <li
                  key={link.id}
                  style={{
                    padding: "8px 10px", marginBottom: 6, borderRadius: 6,
                    background: "#f5f7fa", border: "1px solid #d5dde8",
                    display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                  }}
                >
                  <strong>{LINK_TYPE_LABELS[link.link_type]}</strong>
                  <a href={link.url} target="_blank" rel="noreferrer" style={{ wordBreak: "break-all" }}>
                    {link.label || link.url}
                  </a>
                  {mode === "edit" && (
                    <button
                      type="button"
                      onClick={() => removeLink(link.id)}
                      style={{ border: "none", background: "none", color: "#a33", cursor: "pointer", padding: 0, marginLeft: "auto" }}
                    >
                      Usuń
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {mode === "edit" && !showLinkForm && (
            <button className={"button"} type="button" onClick={() => setShowLinkForm(true)}>
              + Dodaj link
            </button>
          )}
          {mode === "edit" && showLinkForm && (
            <div style={{ marginTop: 8, padding: 8, background: "#f5f7fa", border: "1px solid #d5dde8", borderRadius: 6 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <select
                  value={linkForm.link_type}
                  onChange={(e) => setLinkForm({ ...linkForm, link_type: e.target.value as LinkType })}
                  style={{ padding: "4px 8px" }}
                >
                  {(Object.keys(LINK_TYPE_LABELS) as LinkType[]).map((t) => (
                    <option key={t} value={t}>{LINK_TYPE_LABELS[t]}</option>
                  ))}
                </select>
                <input
                  type="text" placeholder="URL *" value={linkForm.url}
                  onChange={(e) => setLinkForm({ ...linkForm, url: e.target.value })}
                  style={{ padding: "4px 8px", minWidth: 260 }}
                />
                <input
                  type="text" placeholder="Etykieta (opcjonalnie)" value={linkForm.label}
                  onChange={(e) => setLinkForm({ ...linkForm, label: e.target.value })}
                  style={{ padding: "4px 8px", minWidth: 160 }}
                />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                <button className={"button"} type="button" onClick={addLink}>Zapisz link</button>
                <button className={"button"} type="button" onClick={() => { setShowLinkForm(false); setLinkForm(emptyLinkForm); }}>
                  Anuluj
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {!isNew && !isCompanyCategory && whatsappProfile && (
        <div style={{ marginTop: 24 }}>
          <h3>Profil sąsiedzki (WhatsApp)</h3>
          <p style={{ color: "#667", fontSize: "0.85em", marginTop: -6 }}>
            Budowany i aktualizowany automatycznie z czatów WhatsApp — tylko fakty jawnie napisane przez tę osobę o sobie.
          </p>
          <WhatsappProfileView profile={whatsappProfile} latestEvent={latestEvent(contact?.events)} />
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
                  {editingRelId === r.id ? (
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                      <input
                        type="text"
                        value={editRelType}
                        onChange={(e) => setEditRelType(e.target.value)}
                        style={{ padding: "4px 8px", minWidth: 160 }}
                      />
                      <input
                        type="text"
                        value={editRelNote}
                        placeholder="Notatka"
                        onChange={(e) => setEditRelNote(e.target.value)}
                        style={{ padding: "4px 8px", minWidth: 140 }}
                      />
                      <input
                        type="date"
                        value={editRelStartDate}
                        onChange={(e) => setEditRelStartDate(e.target.value)}
                        style={{ padding: "4px 8px" }}
                      />
                      <span>–</span>
                      <input
                        type="date"
                        value={editRelEndDate}
                        onChange={(e) => setEditRelEndDate(e.target.value)}
                        style={{ padding: "4px 8px" }}
                      />
                      <button className={"button"} type="button" onClick={saveEditRelationship}>Zapisz</button>
                      <button className={"button"} type="button" onClick={() => setEditingRelId(null)}>Anuluj</button>
                    </div>
                  ) : (
                    <>
                      <a href={`/contacts/${r.other_contact.id}`}><strong>{otherName(r.other_contact)}</strong></a> — {r.relationship_type}
                      {relDatesLabel(r) && <span style={{ color: "#667" }}> [{relDatesLabel(r)}]</span>}
                      {r.note && <span style={{ color: "#667" }}> ({r.note})</span>}
                      {mode === "edit" && (
                        <>
                          <button
                            type="button"
                            onClick={() => startEditRelationship(r)}
                            style={{ marginLeft: 8, border: "none", background: "none", color: "#458", cursor: "pointer" }}
                          >
                            ✎
                          </button>
                          <button
                            type="button"
                            onClick={() => removeRelationship(r.id)}
                            style={{ marginLeft: 4, border: "none", background: "none", color: "#a33", cursor: "pointer" }}
                          >
                            ✕
                          </button>
                        </>
                      )}
                    </>
                  )}
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
                    <a href={`/contacts/${r.other_contact.id}`}><strong>{otherName(r.other_contact)}</strong></a> — ten kontakt jest dla tej osoby: {r.relationship_type}
                    {relDatesLabel(r) && <span style={{ color: "#667" }}> [{relDatesLabel(r)}]</span>}
                    {r.note && <span style={{ color: "#667" }}> ({r.note})</span>}
                  </li>
                ))}
              </ul>
            </>
          )}

          {mode === "edit" && (
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
                  <option key={c.id} value={c.id}>{otherName(c)}</option>
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
              <input
                type="date"
                value={relStartDate}
                onChange={(e) => setRelStartDate(e.target.value)}
                title="Data rozpoczęcia (opcjonalnie)"
                style={{ padding: "4px 8px" }}
              />
              <span>–</span>
              <input
                type="date"
                value={relEndDate}
                onChange={(e) => setRelEndDate(e.target.value)}
                title="Data zakończenia (opcjonalnie)"
                style={{ padding: "4px 8px" }}
              />
              <button className={"button"} type="button" onClick={addRelationship}>Dodaj powiązanie</button>
            </div>
          </div>
          )}
        </div>
      )}

      {!isNew && (
        <div style={{ marginTop: 24 }}>
          <details>
          <summary style={{ cursor: "pointer", fontSize: "1.17em", fontWeight: "bold", margin: "1em 0" }}>
            Historia zmian ({changeLog.length})
          </summary>
          {changeLog.length === 0 && <p style={{ color: "#667" }}>Brak zapisanej historii.</p>}
          {changeLog.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0 }}>
              {changeLog.map((entry) => (
                <li
                  key={entry.id}
                  style={{
                    padding: "6px 10px", marginBottom: 6, borderRadius: 6,
                    background: "#f5f7fa", border: "1px solid #d5dde8", fontSize: "0.9em",
                  }}
                >
                  <div>
                    <strong>{CHANGE_SOURCE_LABELS[entry.source] ?? entry.source}</strong>
                    <span style={{ color: "#667" }}> — {new Date(entry.created_at).toLocaleString("pl-PL")}</span>
                  </div>
                  {entry.changed_fields.length > 0 && (
                    <div style={{ color: "#667" }}>
                      Zmienione pola: {entry.changed_fields.map(changeFieldLabel).join(", ")}
                    </div>
                  )}
                  {entry.note && <div style={{ color: "#667" }}>{entry.note}</div>}
                </li>
              ))}
            </ul>
          )}
          </details>
        </div>
      )}
    </div>
  );
};

const cite = (zrodlo?: string | null) => (zrodlo ? <span style={{ color: "#89a" }}> ({zrodlo})</span> : null);

const WhatsappProfileView = ({ profile: wp, latestEvent }: {
  profile: WhatsappProfile;
  latestEvent?: ContactGroupEvent | null;
}) => {
  const p = wp.profile;
  const hasFacts = p && (
    p.zawod_lub_branza || p.miejsce_pracy || p.hobby_zainteresowania?.length || p.zwierzeta?.length ||
    p.dzieci || p.urodziny || p.podroze_wakacje?.length || p.wydarzenia_ostatnie?.length || p.zaangazowanie_osiedlowe
  );
  const groups = Object.values(wp.groups || {});

  return (
    <div style={{ padding: 8, background: "#f5f7fa", border: "1px solid #d5dde8", borderRadius: 6 }}>
      {groups.length > 0 && (
        <div style={{ fontSize: "0.85em", color: "#667", marginBottom: 8 }}>
          {groups.map((g, i) => (
            <div key={i}>
              „{g.group_label}” — {g.message_count} wiadomości (od {g.first_date} do {g.last_date})
            </div>
          ))}
        </div>
      )}
      {!hasFacts && <p style={{ color: "#667" }}>Za mało treściwych wiadomości, żeby zbudować profil tej osoby.</p>}
      {hasFacts && p && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {(p.zawod_lub_branza || p.miejsce_pracy) && (
            <div>
              <strong>Czym się zajmuje:</strong>{" "}
              {[p.zawod_lub_branza?.wartosc, p.miejsce_pracy?.wartosc].filter(Boolean).join(" — ")}
              {cite((p.zawod_lub_branza || p.miejsce_pracy)?.zrodlo)}
            </div>
          )}
          {p.hobby_zainteresowania?.length > 0 && (
            <div>
              <strong>Hobby:</strong>{" "}
              {p.hobby_zainteresowania.map((t, i) => (
                <span key={i}>{i > 0 && "; "}{t.wartosc}{cite(t.zrodlo)}</span>
              ))}
            </div>
          )}
          {p.zwierzeta?.length > 0 && (
            <div>
              <strong>Zwierzęta:</strong>{" "}
              {p.zwierzeta.map((z, i) => (
                <span key={i}>{i > 0 && "; "}{z.wartosc}{cite(z.zrodlo)}</span>
              ))}
            </div>
          )}
          {p.dzieci && <div><strong>Rodzina:</strong> {p.dzieci.wartosc}{cite(p.dzieci.zrodlo)}</div>}
          {p.urodziny && <div><strong>Urodziny:</strong> {p.urodziny.wartosc}{cite(p.urodziny.zrodlo)}</div>}
          {p.podroze_wakacje?.length > 0 && (
            <div>
              <strong>Podróże:</strong>{" "}
              {p.podroze_wakacje.map((t, i) => (
                <span key={i}>{i > 0 && "; "}{t.gdzie}{t.kiedy && ` (${t.kiedy})`}{cite(t.zrodlo)}</span>
              ))}
            </div>
          )}
          {p.wydarzenia_ostatnie?.length > 0 && (
            <div>
              <strong>Ostatnie wydarzenia:</strong>{" "}
              {p.wydarzenia_ostatnie.map((t, i) => (
                <span key={i}>{i > 0 && "; "}{t.co}{t.kiedy && ` (${t.kiedy})`}{cite(t.zrodlo)}</span>
              ))}
            </div>
          )}
          {p.zaangazowanie_osiedlowe && (
            <div><strong>Zaangażowanie osiedlowe:</strong> {p.zaangazowanie_osiedlowe.wartosc}{cite(p.zaangazowanie_osiedlowe.zrodlo)}</div>
          )}
        </div>
      )}
      {(wp.suggestions?.length > 0 || latestEvent) && (
        <div style={{ marginTop: 10 }}>
          <strong>Pomysły na rozmowę:</strong>
          <ul style={{ margin: "4px 0 0 0", paddingLeft: 20 }}>
            {latestEvent && (
              <li>
                💬 {eventHintText(latestEvent)}
                {latestEvent.group_id !== null && <>
                  {" "}(<NavLink to={`/contact_groups/${latestEvent.group_id}`}>szczegóły grupy</NavLink>)
                </>}
              </li>
            )}
            {wp.suggestions.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
};

export default Contact;
