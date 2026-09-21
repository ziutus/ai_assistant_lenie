import React from "react";
import axios from "axios";
import { NavLink, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

// Imported chat logs (currently WhatsApp only, backend/imports/whatsapp_chat_import.py) —
// read-only browsing of chat_conversations/chat_messages, backend/library/chat_routes.py.

export interface ChatConversationListItem {
  id: number;
  platform: string;
  chat_key: string;
  display_name: string;
  message_count: number;
  last_imported_at: string | null;
}

const DEFAULT_PAGE_SIZE = 50;

const Chats = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [conversations, setConversations] = React.useState<ChatConversationListItem[]>([]);
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

  const fetchConversations = async (pageArg: number) => {
    setIsLoading(true);
    setIsError(false);
    setMessage("");
    try {
      const params = { offset: String((pageArg - 1) * pageSize), limit: String(pageSize) };
      const response = await axios.get(`${apiUrl}/chat_conversations`, { params, headers });
      const rows: ChatConversationListItem[] = response.data.conversations ?? [];
      setConversations(rows);
      setPage(pageArg);
      setTotal(response.data.total ?? rows.length);
      setSearchParams(pageArg === 1 ? {} : { page: String(pageArg) }, { replace: true });
      if (!rows.length) setMessage("Brak zaimportowanych rozmów.");
    } catch (error: any) {
      console.error("Error fetching chat conversations", error);
      setIsError(true);
      setMessage(`Nie udało się pobrać rozmów: ${error.response?.data?.message || error.message}`);
    }
    setIsLoading(false);
  };

  React.useEffect(() => {
    fetchConversations(initialPage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatDate = (value: string | null) => (value ? new Date(value).toLocaleString("pl-PL") : "—");

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Rozmowy (czaty)</h2>
      <p style={{ color: "#667", marginBottom: 14 }}>
        Pełne logi zaimportowanych czatów (obecnie WhatsApp) — patrz{" "}
        <code>backend/imports/whatsapp_chat_import.py</code>. Tylko do odczytu.
      </p>

      {message && <p className={isError ? "error" : undefined}>{message}</p>}
      {isLoading && <p>Ładowanie...</p>}

      {conversations.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
              <th style={{ padding: "6px 8px" }}>Nazwa</th>
              <th style={{ padding: "6px 8px" }}>Platforma</th>
              <th style={{ padding: "6px 8px" }}>Liczba wiadomości</th>
              <th style={{ padding: "6px 8px" }}>Ostatni import</th>
            </tr>
          </thead>
          <tbody>
            {conversations.map((c) => (
              <tr key={c.id} style={{ borderBottom: "1px solid #eee" }}>
                <td style={{ padding: "6px 8px" }}>
                  <NavLink to={`/chats/${c.id}`}>{c.display_name}</NavLink>
                </td>
                <td style={{ padding: "6px 8px" }}>{c.platform}</td>
                <td style={{ padding: "6px 8px" }}>{c.message_count.toLocaleString("pl")}</td>
                <td style={{ padding: "6px 8px" }}>{formatDate(c.last_imported_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading}
        label="rozmów" onPageChange={(p) => fetchConversations(p)} />
    </div>
  );
};

export default Chats;
