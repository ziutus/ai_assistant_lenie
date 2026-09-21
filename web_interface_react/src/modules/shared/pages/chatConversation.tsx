import React from "react";
import axios from "axios";
import { NavLink, useParams, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";
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
}

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

const MessageMedia = ({ m }: { m: ChatMessageItem }) => {
  if (!m.media_original_filename) return null;
  const sizeLabel = formatSize(m.media_size_bytes);
  if (!m.media_url) {
    return (
      <div style={{ color: "#888", fontStyle: "italic" }}>
        📎 {m.media_original_filename}{sizeLabel ? ` (${sizeLabel})` : ""} — plik niedostępny w eksporcie
      </div>
    );
  }
  if (m.message_type === "image") {
    return (
      <a href={m.media_url} target="_blank" rel="noreferrer">
        <img src={m.media_url} alt={m.media_original_filename}
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
      📄 {m.media_original_filename}{sizeLabel ? ` (${sizeLabel})` : ""}
    </a>
  );
};

const ChatConversation = () => {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [conversation, setConversation] = React.useState<ChatConversationListItem | null>(null);
  const [messages, setMessages] = React.useState<ChatMessageItem[]>([]);
  const [messageType, setMessageType] = React.useState(searchParams.get("message_type") ?? "");
  const [dateFrom, setDateFrom] = React.useState(searchParams.get("date_from") ?? "");
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

  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };

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
      const response = await axios.get(`${apiUrl}/chat_conversations/${id}/messages`, { params, headers });
      setConversation(response.data.conversation ?? null);
      const rows: ChatMessageItem[] = response.data.messages ?? [];
      setMessages(rows);
      setPage(pageArg);
      setTotal(response.data.total ?? rows.length);
      const nextParams: Record<string, string> = {};
      if (pageArg !== 1) nextParams.page = String(pageArg);
      if (messageTypeArg) nextParams.message_type = messageTypeArg;
      if (dateFromArg) nextParams.date_from = dateFromArg;
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
  }, [id]);

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
        <label style={{ marginLeft: 14 }}>
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
            style={{ marginLeft: 8 }}
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

      {message && <p className={isError ? "error" : undefined}>{message}</p>}
      {isLoading && <p>Ładowanie...</p>}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.map((m) => (
          <div key={m.id} style={{ border: "1px solid #eee", borderRadius: 6, padding: "8px 12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, color: "#556", fontSize: "0.9em", marginBottom: 4 }}>
              <strong>
                {m.contact ? (
                  <NavLink to={`/contacts/${m.contact.id}`}>{m.contact.display_name ?? m.sender_name_raw}</NavLink>
                ) : (
                  m.sender_name_raw
                )}
              </strong>
              <span>{formatDate(m.sent_at)}</span>
            </div>
            {m.message_type === "deleted" ? (
              <em style={{ color: "#999" }}>Wiadomość usunięta</em>
            ) : (
              <>
                {m.content && <div style={{ whiteSpace: "pre-line" }}>{m.content}</div>}
                <MessageMedia m={m} />
              </>
            )}
          </div>
        ))}
      </div>

      <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading}
        label="wiadomości" onPageChange={(p) => fetchMessages(p)} />
    </div>
  );
};

export default ChatConversation;
