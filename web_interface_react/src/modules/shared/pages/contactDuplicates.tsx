import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

interface DuplicateContact {
  id: number;
  display_name: string;
  category_name: string | null;
  company: string | null;
  phone_number: string | null;
  email: string | null;
  current_city: string | null;
  photo_thumbnail_url: string | null;
  is_archived: boolean;
}

interface DuplicatePair {
  contact_a: DuplicateContact;
  contact_b: DuplicateContact;
  score: number;
  reasons: string[];
}

const ContactDuplicates = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [pairs, setPairs] = React.useState<DuplicatePair[]>([]);
  const [includeArchived, setIncludeArchived] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(true);
  const [message, setMessage] = React.useState("");
  const [pending, setPending] = React.useState<string[]>([]);
  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  React.useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true); setMessage(""); setPairs([]);
    axios.get(`${apiUrl}/contacts/duplicates`, {
      headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` },
      params: { include_archived: includeArchived ? "1" : "0" }, signal: controller.signal,
    }).then(response => setPairs(response.data.duplicates)).catch(error => {
      if (!controller.signal.aborted) setMessage(`Nie udało się pobrać duplikatów: ${error.response?.data?.message || error.message}`);
    }).finally(() => { if (!controller.signal.aborted) setIsLoading(false); });
    return () => controller.abort();
  }, [apiUrl, apiKey, includeArchived]);

  const dismiss = async (pair: DuplicatePair) => {
    const key = `${pair.contact_a.id}-${pair.contact_b.id}`;
    setPending(current => [...current, key]); setMessage("");
    try {
      await axios.post(`${apiUrl}/contacts/duplicates/dismiss`, {
        contact_id_a: pair.contact_a.id, contact_id_b: pair.contact_b.id,
      }, { headers });
      setPairs(current => current.filter(item => item.contact_a.id !== pair.contact_a.id || item.contact_b.id !== pair.contact_b.id));
    } catch (error: any) {
      setMessage(`Nie udało się odrzucić pary: ${error.response?.data?.message || error.message}`);
    } finally {
      setPending(current => current.filter(item => item !== key));
    }
  };

  return <div className="contact-duplicates">
    <h2>Duplikaty kontaktów</h2>
    <label><input type="checkbox" checked={includeArchived} onChange={event => setIncludeArchived(event.target.checked)} /> Uwzględnij zarchiwizowane</label>
    {isLoading && <div className="loader" />}
    {message && <p className="errorText" role="alert">{message}</p>}
    {!isLoading && !message && pairs.length === 0 && <p>Brak wykrytych duplikatów.</p>}
    {pairs.map(pair => <article className="contact-duplicate-card" key={`${pair.contact_a.id}-${pair.contact_b.id}`}>
      <span className="contact-duplicate-chip">Zgodność: {Math.round(pair.score * 100)}%</span>
      <div className="contact-duplicate-columns">
        {[pair.contact_a, pair.contact_b].map(contact => <div key={contact.id}>
          {contact.photo_thumbnail_url && <img className="contact-duplicate-photo" src={contact.photo_thumbnail_url} alt={`Zdjęcie: ${contact.display_name}`} />}
          <h3><NavLink to={`/contacts/${contact.id}`}>{contact.display_name}</NavLink></h3>
          <p>{contact.category_name} {contact.is_archived && " · Archiwalny"}</p>
          {[contact.company, contact.phone_number, contact.email, contact.current_city].filter(Boolean).map((value, index) => <div key={index}>{value}</div>)}
        </div>)}
      </div>
      <p>{pair.reasons.map(reason => <span className="contact-duplicate-chip" key={reason}>{reason}</span>)}</p>
      <div className="contact-duplicate-actions">
        <NavLink className="button" to={`/contacts/merge?a=${pair.contact_a.id}&b=${pair.contact_b.id}`}>Scal kontakty</NavLink>
        <button className="button" disabled={pending.includes(`${pair.contact_a.id}-${pair.contact_b.id}`)} onClick={() => void dismiss(pair)}>To nie duplikaty</button>
      </div>
    </article>)}
  </div>;
};

export default ContactDuplicates;
