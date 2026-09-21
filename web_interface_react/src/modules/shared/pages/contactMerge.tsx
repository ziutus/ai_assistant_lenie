import React from "react";
import axios from "axios";
import { NavLink, useNavigate, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

const MERGE_FIELDS = [
  ["first_name", "Imię"], ["last_name", "Nazwisko"], ["gender", "Płeć"], ["display_label", "Nazwa robocza"],
  ["phone_number", "Główny telefon"], ["email", "Główny e-mail"], ["company", "Firma"], ["position", "Stanowisko"],
  ["current_city", "Miejscowość"], ["hometown", "Miejscowość rodzinna"], ["birthday", "Data urodzenia"],
  ["birthday_month", "Miesiąc urodzenia"], ["birthday_day", "Dzień urodzenia"], ["pesel", "PESEL"],
  ["notes", "Notatki"], ["private_notes", "Notatki prywatne"], ["category_id", "Kategoria"],
  ["languages", "Języki"], ["nationality", "Obywatelstwo"], ["photo_storage_key", "Zdjęcie"],
  ["photo_thumbnail_storage_key", "Miniatura zdjęcia"],
] as const;
type Field = typeof MERGE_FIELDS[number][0];
type Choices = Record<Field, "primary" | "duplicate">;
interface MergeContact extends Record<string, unknown> {
  id: number;
  display_name: string;
  category_name: string | null;
  photo_url: string | null;
  photo_thumbnail_url: string | null;
  merge_counts: Record<string, number>;
}
const COLLECTIONS = [
  ["groups", "Grupy"], ["interests", "Zainteresowania"], ["phone_numbers", "Telefony"],
  ["email_addresses", "Adresy e-mail"], ["events", "Wydarzenia"], ["relationships", "Powiązania"],
  ["organizations", "Organizacje"], ["addresses", "Adresy"], ["education", "Wykształcenie"], ["links", "Linki"],
];
const isEmpty = (value: unknown) => value == null || value === "" || (Array.isArray(value) && value.length === 0);
const displayValue = (contact: MergeContact, field: Field): React.ReactNode => {
  const value = contact[field];
  if (isEmpty(value)) return "—";
  if (field === "category_id") return contact.category_name;
  if (field === "photo_storage_key" || field === "photo_thumbnail_storage_key") {
    const url = field === "photo_storage_key" ? contact.photo_url : contact.photo_thumbnail_url;
    return url ? <img className="contact-duplicate-photo" src={url} alt="Zdjęcie kontaktu" /> : "Zdjęcie zapisane";
  }
  if (field === "gender") return ({ male: "Mężczyzna", female: "Kobieta", other: "Inna" } as Record<string, string>)[String(value)] || String(value);
  if (field === "languages" && Array.isArray(value)) return value.map(item => `${item.language}${item.native ? " (ojczysty)" : item.level ? ` (${item.level})` : ""}`).join(", ");
  return Array.isArray(value) ? value.join(", ") : String(value);
};
const count = (contact: MergeContact, field: string) => contact.merge_counts[field] ?? (Array.isArray(contact[field]) ? contact[field].length : 0);

const ContactMerge = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const a = params.get("a") || "", b = params.get("b") || "";
  const [contacts, setContacts] = React.useState<[MergeContact, MergeContact] | null>(null);
  const [choices, setChoices] = React.useState<Choices>({} as Choices);
  const [message, setMessage] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(true);
  const [isSaving, setIsSaving] = React.useState(false);
  React.useEffect(() => {
    const controller = new AbortController();
    setContacts(null); setMessage(""); setIsLoading(true);
    if (!/^[1-9]\d*$/.test(a) || !/^[1-9]\d*$/.test(b) || Number(a) === Number(b)) {
      setMessage("Wybierz dwa różne kontakty."); setIsLoading(false);
      return () => controller.abort();
    }
    Promise.all([a, b].map(id => axios.get(`${apiUrl}/contacts/${id}`, {
      headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` }, signal: controller.signal,
    }))).then(responses => {
      const pair = responses.map(response => response.data.contact) as [MergeContact, MergeContact];
      setContacts(pair);
      setChoices(Object.fromEntries(MERGE_FIELDS.map(([field]) => [field,
        isEmpty(pair[0][field]) && !isEmpty(pair[1][field]) ? "duplicate" : "primary",
      ])) as Choices);
    }).catch(error => {
      if (!controller.signal.aborted) setMessage(`Nie udało się pobrać kontaktów: ${error.response?.data?.message || error.message}`);
    }).finally(() => { if (!controller.signal.aborted) setIsLoading(false); });
    return () => controller.abort();
  }, [a, b, apiUrl, apiKey]);
  const merge = async () => {
    if (!contacts || isSaving) return;
    setIsSaving(true); setMessage("");
    try {
      const response = await axios.post(`${apiUrl}/contacts/merge`, {
        primary_contact_id: contacts[0].id, duplicate_contact_id: contacts[1].id, field_choices: choices,
      }, { headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` } });
      navigate(`/contacts/${response.data.contact.id}?merged=1`, { replace: true });
    } catch (error: any) {
      setMessage(`Nie udało się scalić kontaktów: ${error.response?.data?.message || error.message}`);
    } finally { setIsSaving(false); }
  };
  return <div>
    <h2>Scalanie kontaktów</h2>
    {isLoading && <div className="loader" />}
    {message && <p className="errorText" role="alert">{message}</p>}
    {contacts && <>
      <p>Scalenie zachowa kontakt A: <strong>{contacts[0].display_name} (#{contacts[0].id})</strong> i usunie kontakt B: <strong>{contacts[1].display_name} (#{contacts[1].id})</strong>. Wybory poniżej określają wyłącznie zachowane wartości pól.</p>
      <button className="button" disabled={isSaving} onClick={() => navigate(`/contacts/merge?a=${b}&b=${a}`)}>Zamień stronami</button>
      <div className="contact-merge-scroll"><table className="contact-merge-table">
        <thead><tr><th>Pole</th><th>A: {contacts[0].display_name}</th><th>B: {contacts[1].display_name}</th></tr></thead>
        <tbody>{MERGE_FIELDS.map(([field, label]) => <tr key={field}>
          <th scope="row">{label}</th>
          {contacts.map((contact, index) => <td key={contact.id}><label>
            <input type="radio" name={field} disabled={isSaving} checked={choices[field] === (index === 0 ? "primary" : "duplicate")}
              aria-label={`${label}: zachowaj ${index === 0 ? "A" : "B"}`}
              onChange={() => setChoices(current => ({ ...current, [field]: index === 0 ? "primary" : "duplicate" }))} />
            {displayValue(contact, field)}
          </label></td>)}
        </tr>)}</tbody>
      </table></div>
      <h3>Dane łączone automatycznie</h3>
      <p>Wspólne grupy, zainteresowania, kanały i uczestnictwa nie będą powielane. Bezpośrednie powiązania między A i B zostaną usunięte.</p>
      <ul>{COLLECTIONS.map(([field, label]) => <li key={field}>{label}: A — {count(contacts[0], field)}, B — {count(contacts[1], field)}</li>)}</ul>
      <button className="button" disabled={isSaving} onClick={() => void merge()}>{isSaving ? "Scalanie…" : "Scal kontakty"}</button>
    </>}
    {!isSaving && <p><NavLink to="/contacts/duplicates">Wróć</NavLink></p>}
  </div>;
};

export default ContactMerge;
