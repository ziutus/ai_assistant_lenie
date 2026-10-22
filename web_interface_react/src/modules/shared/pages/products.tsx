import React from "react";
import axios from "axios";
import { Link, useSearchParams } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";
import { Pagination, PAGE_SIZES } from "../components/Pagination/pagination";

// Products and systems ("Starlink", "Starshield") that a reviewer marked in document texts on /ner/:id
// (document_entities, entity_type productName), grouped by name across documents. Each row links to the
// product's own page (/products/:name).

interface ProductDocument { id: number; title: string | null; mentions: number; entity_id: number }
interface ProductRow { name: string; description: string | null; mentions: number; document_count: number; documents: ProductDocument[] }

const DEFAULT_PAGE_SIZE = 50;

const Products = () => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";
  const requestedPageSize = Number(searchParams.get("page_size") ?? DEFAULT_PAGE_SIZE);
  const pageSize = PAGE_SIZES.includes(requestedPageSize) ? requestedPageSize : DEFAULT_PAGE_SIZE;
  const requestedPage = Number(searchParams.get("page") ?? "1");
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const [queryText, setQueryText] = React.useState(q);
  const [rows, setRows] = React.useState<ProductRow[]>([]);
  const [total, setTotal] = React.useState(0);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const headers = React.useMemo(() => ({ "x-api-key": apiKey ?? "" }), [apiKey]);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    setSearchParams(next, { replace: true });
  };

  React.useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError("");
    axios.get(`${apiUrl}/entity_products`, { headers, params: { q, limit: pageSize, offset: (page - 1) * pageSize } })
      .then((response) => {
        if (cancelled) return;
        setRows(response.data.products ?? []);
        setTotal(response.data.total ?? 0);
      })
      .catch((reason: any) => {
        if (!cancelled) setError(`Nie udało się pobrać produktów: ${reason.response?.data?.message || reason.message}`);
      })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [apiUrl, headers, q, page, pageSize]);

  return (
    <div>
      <h2 style={{ marginBottom: 6 }}>Produkty i systemy</h2>
      <p style={{ color: "#667", marginBottom: 10 }}>
        Produkty, usługi i systemy (np. Starlink, Starshield), które oznaczyłeś w tekstach dokumentów prawym klawiszem
        na stronie NER. Kliknij nazwę, żeby zobaczyć stronę produktu.
      </p>
      <form onSubmit={(event) => { event.preventDefault(); update({ q: queryText.trim() || null, page: null }); }}
        style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginBottom: 8 }}>
        <input type="search" aria-label="Szukaj produktu" placeholder="Szukaj w nazwie i opisie…" value={queryText}
          onChange={(event) => setQueryText(event.target.value)} style={{ padding: "4px 8px" }} />
        <button type="submit" className="button">Szukaj</button>
        <span style={{ color: "#64748b" }}>{isLoading ? "Wczytuję…" : `${total} produktów`}</span>
      </form>
      {error && <p role="alert" style={{ color: "#a33" }}>{error}</p>}
      {!isLoading && !error && rows.length === 0 && <p style={{ color: "#667" }}>Brak produktów.</p>}
      <ul aria-label="Produkty" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {rows.map((row) => (
          <li key={row.name.toLowerCase()} style={{ padding: "8px 10px", marginBottom: 8, border: "1px solid #e2e8f0", borderRadius: 6, background: "#fff" }}>
            <Link to={`/products/${encodeURIComponent(row.name)}`} style={{ fontWeight: 600 }}>🛰️ {row.name}</Link>{" "}
            <span style={{ color: "#64748b", fontSize: "0.85em" }}>{row.document_count} dok. · {row.mentions} wzmianek</span>
            <div style={{ margin: "4px 0", color: row.description ? undefined : "#94a3b8" }}>
              {row.description || "Brak opisu — dodaj go na stronie produktu."}
            </div>
          </li>
        ))}
      </ul>
      <Pagination page={page} pageSize={pageSize} total={total} isLoading={isLoading} label="produktów"
        onPageChange={(next) => update({ page: next > 1 ? String(next) : null })} />
    </div>
  );
};

export default Products;
