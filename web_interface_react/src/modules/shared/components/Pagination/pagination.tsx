import React from "react";

export const PAGE_SIZES = [25, 50, 100];

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  isLoading?: boolean;
  label: string;
  onPageChange: (page: number) => void;
}

export const Pagination = ({ page, pageSize, total, isLoading = false, label, onPageChange }: PaginationProps) => {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const visiblePages = Array.from({ length: totalPages }, (_, index) => index + 1)
    .filter(number => number === 1 || number === totalPages || Math.abs(number - page) <= 2);

  if (totalPages <= 1) return null;
  return (
    <nav aria-label={`Stronicowanie ${label}`} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, padding: "14px 0 8px" }}>
      <button type="button" className="button" disabled={isLoading || page <= 1} onClick={() => onPageChange(page - 1)}>Poprzednia</button>
      {visiblePages.map((number, index) => <React.Fragment key={number}>
        {visiblePages[index - 1] && number - visiblePages[index - 1] > 1 && <span>…</span>}
        <button type="button" className="button" disabled={isLoading || number === page} aria-current={number === page ? "page" : undefined}
          onClick={() => onPageChange(number)} style={{ minWidth: 36, opacity: number === page ? .6 : 1 }}>{number}</button>
      </React.Fragment>)}
      <button type="button" className="button" disabled={isLoading || page >= totalPages} onClick={() => onPageChange(page + 1)}>Następna</button>
      <label style={{ display: "flex", alignItems: "center", gap: 5, marginLeft: 8 }}>Strona
        <select value={Math.min(page, totalPages)} disabled={isLoading} onChange={event => onPageChange(Number(event.target.value))}>
          {Array.from({ length: totalPages }, (_, index) => index + 1).map(number => <option key={number} value={number}>{number}</option>)}
        </select> z {totalPages}
      </label>
    </nav>
  );
};
