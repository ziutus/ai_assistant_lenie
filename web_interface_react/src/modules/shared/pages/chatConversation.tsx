import React from "react";
import axios from "axios";
import { NavLink, useParams, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";
import RadarSelectionMenu from "../components/RadarSelectionMenu/radarSelectionMenu";
import type { ChatConversationListItem } from "./chats";

// Message thread view for one imported chat conversation — see chats.tsx.

interface ChatContactSummary {
  id: number;
  display_name: string | null;
}

interface ChatMessageItem {
  id: number;
  sender_name_raw: string;
  contact: ChatContactSummary | null;
  sent_at: string | null;
  message_type: string;
  content: string | null;
  media_url: string | null;
  media_original_filename: string | null;
  media_mime_type: string | null;
  media_size_bytes: number | null;
  // live-sync fields (absent/null for rows from TXT/ZIP imports)
  source?: string;
  is_from_me?: boolean | null;
  edited_at?: string | null;
  deleted_at?: string | null;
  media_status?: "pending" | "downloaded" | "unavailable" | "error" | null;
  // sender not in the contact book / links written in the text (live-sync and TXT rows alike)
  sender_phone?: string | null;
  sender_nickname?: string | null;
  can_add_contact?: boolean;
  urls?: MessageUrl[];
}

interface MessageUrl {
  url: string;
  document: { id: number; title: string | null; document_type: string } | null;
}

const MEDIA_STATUS_LABELS: Record<string, string> = {
  pending: "załącznik oczekuje na pobranie",
  unavailable: "załącznik niedostępny (WhatsApp go już nie udostępnia lub jest za duży)",
  error: "nie udało się pobrać załącznika po kilku próbach",
};

const DEFAULT_PAGE_SIZE = 100;
const MESSAGE_TYPES = [
  { value: "", label: "Wszystkie typy" },
  { value: "text", label: "Tekst" },
  { value: "image", label: "Obrazy" },
  { value: "video", label: "Filmy" },
  { value: "audio", label: "Nagrania głosowe" },
  { value: "document", label: "Dokumenty" },
  { value: "contact_card", label: "Wizytówki" },
  { value: "deleted", label: "Usunięte" },
];

const formatDate = (value: string | null) => (value ? new Date(value).toLocaleString("pl-PL") : "—");

const formatSize = (bytes: number | null) => {
  if (!bytes) return null;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

interface TopicOption {
  id: number;
  name: string;
}

const AddToTopicButton = ({ messageId, topics, apiUrl, headers }: {
  messageId: number; topics: TopicOption[]; apiUrl: string; headers: Record<string, string>;
}) => {
  const [open, setOpen] = React.useState(false);
  const [topicId, setTopicId] = React.useState("");
  const [status, setStatus] = React.useState<"idle" | "saving" | "done" | "error">("idle");

  if (!topics.length) return null;

  if (status === "done") {
    const topicName = topics.find((t) => String(t.id) === topicId)?.name;
    return <span style={{ fontSize: "0.85em", color: "#2a7" }}>✓ Dodano do „{topicName}”</span>;
  }

  if (!open) {
    return (
      <button type="button" className="button" style={{ fontSize: "0.8em", padding: "2px 8px" }}
        onClick={() => setOpen(true)}>
        📌 Dodaj do tematu
      </button>
    );
  }

  const add = async () => {
    if (!topicId) return;
    setStatus("saving");
    try {
      await axios.post(`${apiUrl}/topics/${topicId}/items`,
        { entity_type: "chat_message", entity_id: messageId }, { headers });
      setStatus("done");
    } catch (error: any) {
      console.error("Error adding chat message to topic", error);
      setStatus("error");
    }
  };

  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: "0.85em" }}>
      <select value={topicId} onChange={(e) => setTopicId(e.target.value)} disabled={status === "saving"}>
        <option value="">Wybierz temat...</option>
        {topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
      </select>
      <button type="button" className="button" disabled={!topicId || status === "saving"} onClick={add}>
        Dodaj
      </button>
      {status === "error" && <span style={{ color: "#c00" }}>Nie udało się dodać</span>}
    </span>
  );
};

type MentionMap = Record<string, { contact: ChatContactSummary | null; name: string | null }>;

// WhatsApp writes a mention as "@<id>"; the backend resolves the ids it knows to a contact or a name.
const MessageText = ({ text, mentions }: { text: string; mentions: MentionMap }) => (
  <>
    {text.split(/(@\d{8,20})/).map((part, index) => {
      const known = part.startsWith("@") ? mentions[part.slice(1)] : undefined;
      if (!known) return <React.Fragment key={index}>{part}</React.Fragment>;
      return known.contact ? (
        <NavLink key={index} to={`/contacts/${known.contact.id}`} title={part}>
          @{known.contact.display_name ?? known.name}
        </NavLink>
      ) : (
        <span key={index} title={part}>@{known.name}</span>
      );
    })}
  </>
);

const PHOTO_RESULT_LABELS: Record<string, string> = {
  stored: "zdjęcie z WhatsAppa zapisane",
  none: "brak zdjęcia profilowego w WhatsAppie",
  unavailable: "nie udało się pobrać zdjęcia (most WhatsApp niedostępny)",
  skipped: "",
};

// Adds the sender of a message to the private contact book: nickname (WhatsApp name), phone, profile
// picture and a note + group naming this chat as the place where the two met.
const AddContactButton = ({ m, channel, apiUrl, headers }: {
  m: ChatMessageItem; channel: string; apiUrl: string; headers: Record<string, string>;
}) => {
  const [open, setOpen] = React.useState(false);
  const [label, setLabel] = React.useState(m.sender_nickname ?? "");
  const [fetchPhoto, setFetchPhoto] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [result, setResult] = React.useState<{ contact_id: number; created: boolean; photo: string } | null>(null);
  const [hint, setHint] = React.useState("");

  // WhatsApp often does not put the name in the message itself; ask what the account knows about the sender.
  const openForm = async () => {
    setOpen(true);
    if (label) return;
    try {
      const response = await axios.get(`${apiUrl}/chat_messages/${m.id}/sender_profile`, { headers });
      const { nickname, source } = response.data;
      if (nickname) {
        setLabel(nickname);
        setHint(source === "address_book" ? "nazwa z Twojej książki telefonicznej" : "nazwa ustawiona przez tę osobę w WhatsAppie");
      } else {
        setHint("WhatsApp nie zna nazwy tej osoby — wpisz własną");
      }
    } catch {
      setHint("nie udało się zapytać WhatsAppa o nazwę");
    }
  };

  if (result) {
    return (
      <span style={{ fontSize: "0.85em", color: "#2a7" }}>
        ✓ {result.created ? "Dodano" : "Powiązano z istniejącym"} kontakt{" "}
        <NavLink to={`/contacts/${result.contact_id}`}>#{result.contact_id}</NavLink>
        {PHOTO_RESULT_LABELS[result.photo] ? ` — ${PHOTO_RESULT_LABELS[result.photo]}` : ""}
      </span>
    );
  }
  if (!open) {
    return (
      <button type="button" className="button" style={{ fontSize: "0.8em", padding: "2px 8px" }}
        title="Dodaj nadawcę do kontaktów — z informacją, że znacie się z tego kanału WhatsApp"
        onClick={openForm}>
        👤 Dodaj do kontaktów
      </button>
    );
  }
  const save = async () => {
    setBusy(true); setError("");
    try {
      const response = await axios.post(`${apiUrl}/chat_messages/${m.id}/create_contact`,
        { display_label: label.trim() || undefined, fetch_photo: fetchPhoto }, { headers });
      setResult(response.data);
    } catch (cause: any) {
      setError(cause.response?.data?.message || cause.message);
    } finally { setBusy(false); }
  };
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap", fontSize: "0.85em" }}>
      <input value={label} placeholder="Pseudonim / nazwa" onChange={(e) => setLabel(e.target.value)} />
      {hint && <span style={{ color: "#667" }}>({hint})</span>}
      <label><input type="checkbox" checked={fetchPhoto} onChange={(e) => setFetchPhoto(e.target.checked)} /> zdjęcie z WhatsAppa</label>
      <button type="button" className="button" disabled={busy} onClick={() => void save()}>
        Zapisz (kanał: {channel})
      </button>
      <button type="button" className="button" disabled={busy} onClick={() => setOpen(false)}>Anuluj</button>
      {error && <span role="alert" style={{ color: "#c00" }}>{error}</span>}
    </span>
  );
};

// Links written in a message: add one to the library (YouTube as a video, anything else as a page).
const MessageUrls = ({ m, apiUrl, headers }: { m: ChatMessageItem; apiUrl: string; headers: Record<string, string> }) => {
  const [urls, setUrls] = React.useState<MessageUrl[]>(m.urls ?? []);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState("");
  if (!urls.length) return null;

  const add = async (url: string) => {
    setBusy(url); setError("");
    try {
      const response = await axios.post(`${apiUrl}/chat_messages/${m.id}/import_url`, { url }, { headers });
      const { document_id: id, document_type: type, promotion_failed: failed } = response.data;
      setUrls((prev) => prev.map((u) => (u.url === url ? { url, document: { id, title: null, document_type: type } } : u)));
      if (failed) setError(`Dodano jako link, ale treści nie udało się pobrać (${failed}).`);
    } catch (cause: any) {
      setError(cause.response?.data?.message || cause.message);
    } finally { setBusy(null); }
  };

  return (
    <div style={{ marginTop: 4, fontSize: "0.85em" }}>
      {urls.map((u) => (
        <div key={u.url}>
          🔗 <a href={u.url} target="_blank" rel="noreferrer">{u.url}</a>{" "}
          {u.document ? (
            <NavLink to={`/${u.document.document_type === "link" ? "link" : u.document.document_type === "youtube" ? "youtube" : "webpage"}/${u.document.id}`}>
              ✓ w bazie wiedzy (#{u.document.id})
            </NavLink>
          ) : (
            <button type="button" className="button" style={{ fontSize: "0.9em", padding: "1px 6px" }} disabled={busy === u.url}
              onClick={() => void add(u.url)}>
              {busy === u.url ? "Dodaję…" : "＋ Dodaj do bazy wiedzy"}
            </button>
          )}
        </div>
      ))}
      {error && <span role="alert" style={{ color: "#c00" }}>{error}</span>}
    </div>
  );
};

const MessageMedia = ({ m }: { m: ChatMessageItem }) => {
  if (!m.media_original_filename && !m.media_url && !m.media_status) return null;
  const sizeLabel = formatSize(m.media_size_bytes);
  const fileLabel = m.media_original_filename || m.media_mime_type || m.message_type;
  if (!m.media_url) {
    const reason = m.media_status ? MEDIA_STATUS_LABELS[m.media_status] : "plik niedostępny w eksporcie";
    return (
      <div style={{ color: "#888", fontStyle: "italic" }}>
        📎 {fileLabel}{sizeLabel ? ` (${sizeLabel})` : ""} — {reason}
      </div>
    );
  }
  if (m.message_type === "image") {
    return (
      <a href={m.media_url} target="_blank" rel="noreferrer">
        <img src={m.media_url} alt={fileLabel}
          style={{ maxWidth: 260, maxHeight: 260, borderRadius: 4, display: "block" }} />
      </a>
    );
  }
  if (m.message_type === "video") {
    return <video src={m.media_url} controls style={{ maxWidth: 320, maxHeight: 320 }} />;
  }
  if (m.message_type === "audio") {
    return <audio src={m.media_url} controls />;
  }
  return (
    <a href={m.media_url} target="_blank" rel="noreferrer">
      📄 {fileLabel}{sizeLabel ? ` (${sizeLabel})` : ""}
    </a>
  );
};

const ChatConversation = () => {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [conversation, setConversation] = React.useState<ChatConversationListItem | null>(null);
  const [messages, setMessages] = React.useState<ChatMessageItem[]>([]);
  const [mentions, setMentions] = React.useState<MentionMap>({});
  const [messageType, setMessageType] = React.useState(searchParams.get("message_type") ?? "");
  const [dateFrom, setDateFrom] = React.useState(searchParams.get("date_from") ?? "");
  const contactId = searchParams.get("contact_id") ?? "";
  const requestedPageSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const initialPageSize = PAGE_SIZES.includes(requestedPageSize) ? requestedPageSize : DEFAULT_PAGE_SIZE;
  const requestedPage = Number(searchParams.get("page") ?? "1");
  const initialPage = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const [page, setPage] = React.useState(initialPage);
  const [pageSize] = React.useState(initialPageSize);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const [contactLabel, setContactLabel] = React.useState<string | null>(null);
  const [topics, setTopics] = React.useState<TopicOption[]>([]);

  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

  React.useEffect(() => {
    axios.get(`${apiUrl}/topics`, { params: { limit: 100 }, headers: { "x-api-key": `${apiKey}` } })
      .then((response) => setTopics(response.data.topics ?? []))
      .catch((error) => console.error("Error fetching topics", error));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchMessages = async (pageArg: number, messageTypeArg = messageType, dateFromArg = dateFrom) => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const params: Record<string, string> = {
        offset: String((pageArg - 1) * pageSize),
        limit: String(pageSize),
      };
      if (messageTypeArg) params.message_type = messageTypeArg;
      if (dateFromArg) params.date_from = dateFromArg;
      if (contactId) params.contact_id = contactId;
      const response = await axios.get(`${apiUrl}/chat_conversations/${id}/messages`, { params, headers });
      setConversation(response.data.conversation ?? null);
      const rows: ChatMessageItem[] = response.data.messages ?? [];
      setMessages(rows);
      setMentions(response.data.mentions ?? {});
      if (contactId) {
        const match = rows.find((m) => String(m.contact?.id) === contactId);
        if (match?.contact?.display_name) setContactLabel(match.contact.display_name);
      }
      setPage(pageArg);
      setTotal(response.data.total ?? rows.length);
      const nextParams: Record<string, string> = {};
      if (pageArg !== 1) nextParams.page = String(pageArg);
      if (messageTypeArg) nextParams.message_type = messageTypeArg;
      if (dateFromArg) nextParams.date_from = dateFromArg;
      if (contactId) nextParams.contact_id = contactId;
      setSearchParams(nextParams, { replace: true });
      if (!rows.length) setMessage("Brak wiadomości pasujących do filtra.");
    } catch (error: any) {
      console.error("Error fetching chat messages", error);
      setIsError(true);
      setMessage(`Nie udało się pobrać wiadomości: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchMessages(initialPage, messageType, dateFrom);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, contactId]);

  return (
    <div>
      <NavLink to="/chats">← Wszystkie rozmowy</NavLink>
      <h2 style={{ margin: "10px 0" }}>{conversation?.display_name ?? `Rozmowa #${id}`}</h2>
      {conversation && (
        <p style={{ color: "#667", marginBottom: 14 }}>
          {conversation.platform} · {conversation.message_count.toLocaleString("pl")} wiadomości łącznie ·
          {" "}ostatni import: {formatDate(conversation.last_imported_at)}
        </p>
      )}

      {contactId && (
        <p style={{ background: "#eef6ff", padding: "8px 10px", borderRadius: 6, marginBottom: 14 }}>
          Pokazuję tylko wiadomości: <strong>{contactLabel ?? `kontakt #${contactId}`}</strong>
          {" — "}
          <NavLink to={`/chats/${id}`}>pokaż wszystkie</NavLink>
        </p>
      )}

      <div style={{ marginBottom: 14 }}>
        <label>
          Typ wiadomości:{" "}
          <select
            value={messageType}
            disabled={isLoading}
            onChange={(e) => {
              setMessageType(e.target.value);
              fetchMessages(1, e.target.value);
            }}
          >
            {MESSAGE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </label>
        <label style={{ marginLeft: 12 }}>
          Od dnia:{" "}
          <input
            type="date"
            value={dateFrom}
            disabled={isLoading}
            onChange={(e) => {
              setDateFrom(e.target.value);
              fetchMessages(1, messageType, e.target.value);
            }}
          />
        </label>
        {dateFrom && (
          <button
            type="button"
            className="button"
            style={{ marginLeft: 12 }}
            disabled={isLoading}
            onClick={() => {
              setDateFrom("");
              fetchMessages(1, messageType, "");
            }}
          >
            Wyczyść
          </button>
        )}
      </div>

      <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading}
        label="wiadomości" onPageChange={(p) => fetchMessages(p)} />

      {message && <p className={isError ? "error" : undefined}>{message}</p>}
      {isLoading && <p>Ładowanie...</p>}

      <RadarSelectionMenu apiUrl={apiUrl} headers={headers}
        sourceContext={`WhatsApp: ${conversation?.display_name ?? `rozmowa #${id}`}`}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.map((m) => (
          <div key={m.id} style={{ border: "1px solid #eee", borderRadius: 6, padding: "8px 12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, color: "#556", fontSize: "0.9em", marginBottom: 4 }}>
              <span style={{ display: "inline-flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <strong>
                  {m.contact ? (
                    <NavLink to={`/contacts/${m.contact.id}`}>{m.contact.display_name ?? m.sender_name_raw}</NavLink>
                  ) : m.is_from_me || /^[+\d]/.test(m.sender_name_raw) ? (
                    m.sender_name_raw
                  ) : (
                    // like WhatsApp: a name chosen by the sender, not saved in the contact book, is marked with ~
                    <span title="Nie ma w książce kontaktów — to nazwa ustawiona przez tę osobę w WhatsAppie">
                      ~{m.sender_name_raw}
                    </span>
                  )}
                </strong>
                {m.can_add_contact && (
                  <AddContactButton m={m} channel={conversation?.display_name ?? `#${id}`} apiUrl={apiUrl}
                    headers={headers} />
                )}
              </span>
              <span>
                {formatDate(m.sent_at)}
                {contactId && m.sent_at && (
                  <>
                    {" "}
                    <a href={`/chats/${id}?date_from=${m.sent_at.slice(0, 10)}`} title="Zobacz całą rozmowę od tej daty">
                      🔗
                    </a>
                  </>
                )}
              </span>
            </div>
            {m.message_type === "deleted" ? (
              <em style={{ color: "#999" }}>Wiadomość usunięta</em>
            ) : (
              <>
                {m.content && (
                  <div style={{ whiteSpace: "pre-line" }}
                    data-radar-context={`${m.sender_name_raw}, ${formatDate(m.sent_at)}`}>
                    <MessageText text={m.content} mentions={mentions} />
                  </div>
                )}
                <MessageUrls m={m} apiUrl={apiUrl} headers={headers} />
                {m.edited_at && (
                  <div style={{ color: "#888", fontSize: 12 }}>
                    (edytowana {new Date(m.edited_at).toLocaleString("pl-PL")})
                  </div>
                )}
                <MessageMedia m={m} />
              </>
            )}
            <div style={{ marginTop: 6, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <AddToTopicButton messageId={m.id} topics={topics} apiUrl={apiUrl} headers={headers} />
            </div>
          </div>
        ))}
      </div>
      </RadarSelectionMenu>

      <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading}
        label="wiadomości" onPageChange={(p) => fetchMessages(p)} />
    </div>
  );
};

export default ChatConversation;
