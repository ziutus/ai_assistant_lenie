import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { defaultChoices } from "../utils/contactMerge";
import { isNameOnlyPhoneConflict } from "../utils/contactDuplicatePhones";

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
  created_at: string | null;
}

interface DuplicatePair {
  contact_a: DuplicateContact;
  contact_b: DuplicateContact;
  score: number;
  reasons: string[];
  auto_mergeable: boolean;
}

const ContactDuplicates = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const hidePhoneConflict = searchParams.get("hide_phone_conflict") === "1";
  const [pairs, setPairs] = React.useState<DuplicatePair[]>([]);
  const [includeArchived, setIncludeArchived] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(true);
  const [message, setMessage] = React.useState("");
  const [pending, setPending] = React.useState<string[]>([]);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [bulkPending, setBulkPending] = React.useState(false);
  const [confirmMerge, setConfirmMerge] = React.useState<string | null>(null);
  const [mergePending, setMergePending] = React.useState(false);
  const [refresh, setRefresh] = React.useState(0);
  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };
  const visiblePairs = React.useMemo(() => hidePhoneConflict
    ? pairs.filter(pair => !isNameOnlyPhoneConflict(pair)) : pairs, [pairs, hidePhoneConflict]);
  const hiddenCount = pairs.length - visiblePairs.length;
  const selectedPairs = visiblePairs.filter(pair => selected.has(`${pair.contact_a.id}-${pair.contact_b.id}`));

  React.useEffect(() => {
    const visibleKeys = new Set(visiblePairs.map(pair => `${pair.contact_a.id}-${pair.contact_b.id}`));
    setSelected(current => new Set([...current].filter(key => visibleKeys.has(key))));
  }, [visiblePairs]);

  React.useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true); setMessage(""); setPairs([]);
    setSelected(new Set());
    setConfirmMerge(null);
    axios.get(`${apiUrl}/contacts/duplicates`, {
      headers: { "Content-Type": "application/json", "x-api-key": `${apiKey}` },
      params: { include_archived: includeArchived ? "1" : "0" }, signal: controller.signal,
    }).then(response => setPairs(response.data.duplicates)).catch(error => {
      if (!controller.signal.aborted) setMessage(`Nie udało się pobrać duplikatów: ${error.response?.data?.message || error.message}`);
    }).finally(() => { if (!controller.signal.aborted) setIsLoading(false); });
    return () => controller.abort();
  }, [apiUrl, apiKey, includeArchived, refresh]);

  const merge = async (pair: DuplicatePair) => {
    if (mergePending || bulkPending || pending.length > 0 || !pair.auto_mergeable) return;
    const key = `${pair.contact_a.id}-${pair.contact_b.id}`;
    if (confirmMerge !== key) { setConfirmMerge(key); return; }
    setConfirmMerge(null); setMergePending(true); setMessage("");
    try {
      const ordered = [pair.contact_a, pair.contact_b].sort((a, b) => {
        const first = a.created_at ? Date.parse(a.created_at) : 0;
        const second = b.created_at ? Date.parse(b.created_at) : 0;
        return first - second || a.id - b.id;
      });
      const responses = await Promise.all(ordered.map(contact =>
        axios.get(`${apiUrl}/contacts/${contact.id}`, { headers })));
      await axios.post(`${apiUrl}/contacts/merge`, {
        primary_contact_id: ordered[0].id, duplicate_contact_id: ordered[1].id,
        field_choices: defaultChoices(responses[0].data.contact, responses[1].data.contact),
      }, { headers });
      setPairs([]); setSelected(new Set()); setIsLoading(true);
      setRefresh(current => current + 1);
    } catch (error: any) {
      setMessage(`Nie udało się scalić kontaktów: ${error.response?.data?.message || error.message}`);
    } finally { setMergePending(false); }
  };

  const dismiss = async (pair: DuplicatePair) => {
    const key = `${pair.contact_a.id}-${pair.contact_b.id}`;
    setPending(current => [...current, key]); setMessage("");
    try {
      await axios.post(`${apiUrl}/contacts/duplicates/dismiss`, {
        contact_id_a: pair.contact_a.id, contact_id_b: pair.contact_b.id,
      }, { headers });
      setPairs(current => current.filter(item => item.contact_a.id !== pair.contact_a.id || item.contact_b.id !== pair.contact_b.id));
      setSelected(current => { const next = new Set(current); next.delete(key); return next; });
    } catch (error: any) {
      setMessage(`Nie udało się odrzucić pary: ${error.response?.data?.message || error.message}`);
    } finally {
      setPending(current => current.filter(item => item !== key));
    }
  };

  const dismissSelected = async () => {
    if (selectedPairs.length === 0 || bulkPending || pending.length > 0) return;
    const dismissedKeys = new Set(selectedPairs.map(pair => `${pair.contact_a.id}-${pair.contact_b.id}`));
    setBulkPending(true);
    try {
      await axios.post(`${apiUrl}/contacts/duplicates/dismiss_bulk`, {
        pairs: selectedPairs.map(pair => ({ contact_id_a: pair.contact_a.id, contact_id_b: pair.contact_b.id })),
      }, { headers });
      setPairs(current => current.filter(pair => !dismissedKeys.has(`${pair.contact_a.id}-${pair.contact_b.id}`)));
      setSelected(new Set()); setMessage("");
    } catch (error: any) {
      setMessage(`Nie udało się odrzucić zaznaczonych par: ${error.response?.data?.message || error.message}`);
    } finally {
      setBulkPending(false);
    }
  };

  return <div className="contact-duplicates">
    <h2>Duplikaty kontaktów</h2>
    <label className="contact-duplicate-selection"><input type="checkbox" checked={hidePhoneConflict}
      disabled={bulkPending || mergePending}
      onChange={event => {
        const checked = event.target.checked;
        setSearchParams(current => {
          const next = new URLSearchParams(current);
          if (checked) next.set("hide_phone_conflict", "1"); else next.delete("hide_phone_conflict");
          return next;
        });
      }} /> Ukryj pary z różnymi numerami telefonu</label>
    <label><input type="checkbox" checked={includeArchived} disabled={bulkPending || mergePending} onChange={event => setIncludeArchived(event.target.checked)} /> Uwzględnij zarchiwizowane</label>
    <div className="contact-duplicate-toolbar">
      <label className="contact-duplicate-selection">
        <input type="checkbox" checked={visiblePairs.length > 0 && selectedPairs.length === visiblePairs.length}
          ref={input => { if (input) input.indeterminate = selectedPairs.length > 0 && selectedPairs.length < visiblePairs.length; }}
          disabled={isLoading || bulkPending || visiblePairs.length === 0}
          onChange={event => setSelected(event.target.checked
            ? new Set(visiblePairs.map(pair => `${pair.contact_a.id}-${pair.contact_b.id}`)) : new Set())} />
        Zaznacz wszystkie
      </label>
      <span>Zaznaczono: {selectedPairs.length}</span>
      <button className="button" disabled={selectedPairs.length === 0 || bulkPending || mergePending || pending.length > 0}
        onClick={() => void dismissSelected()}>Oznacz zaznaczone jako to nie duplikaty</button>
    </div>
    {isLoading && <div className="loader" />}
    {message && <p className="errorText" role="alert">{message}</p>}
    {hiddenCount > 0 && <p>Ukryto {hiddenCount} par z różnymi numerami telefonu</p>}
    {!isLoading && !message && visiblePairs.length === 0 && <p>{hiddenCount > 0
      ? "Brak par do wyświetlenia po zastosowaniu filtra." : "Brak wykrytych duplikatów."}</p>}
    {visiblePairs.map(pair => <article className="contact-duplicate-card" key={`${pair.contact_a.id}-${pair.contact_b.id}`}>
      <label className="contact-duplicate-selection">
        <input type="checkbox" checked={selected.has(`${pair.contact_a.id}-${pair.contact_b.id}`)}
          disabled={bulkPending}
          onChange={event => {
            const checked = event.target.checked;
            const key = `${pair.contact_a.id}-${pair.contact_b.id}`;
            setSelected(current => {
              const next = new Set(current);
              if (checked) next.add(key); else next.delete(key);
              return next;
            });
          }} />
        Zaznacz parę
      </label>
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
        {pair.auto_mergeable && <button className="button" disabled={bulkPending || mergePending || pending.length > 0}
          onClick={() => void merge(pair)}>
          {confirmMerge === `${pair.contact_a.id}-${pair.contact_b.id}` ? "Na pewno?" : "Scal od razu"}
        </button>}
        <button className="button" disabled={bulkPending || mergePending || pending.includes(`${pair.contact_a.id}-${pair.contact_b.id}`)} onClick={() => void dismiss(pair)}>To nie duplikaty</button>
      </div>
    </article>)}
  </div>;
};

export default ContactDuplicates;
