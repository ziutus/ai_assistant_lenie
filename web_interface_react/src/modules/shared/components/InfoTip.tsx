import React from "react";

/** Small ⓘ button that toggles a popup with a longer explanation (keeps section headings compact). */
const InfoTip = ({ label, children }: { label: string; children: React.ReactNode }) => {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLSpanElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-block", marginLeft: 6, fontSize: "0.7em", verticalAlign: "middle" }}>
      <button type="button" aria-label={label} aria-expanded={open} title={label}
        onClick={() => setOpen(v => !v)}
        style={{ border: "none", background: "none", cursor: "pointer", padding: 2, fontSize: "1.2em", lineHeight: 1 }}>
        ⓘ
      </button>
      {open && (
        <span role="note" style={{
          position: "absolute", left: 0, top: "100%", zIndex: 20, width: 300, maxWidth: "80vw",
          padding: "8px 10px", background: "#fff", color: "#334", border: "1px solid #ccd",
          borderRadius: 6, boxShadow: "0 2px 8px rgba(0,0,0,.15)", fontSize: "1.25em", fontWeight: "normal", lineHeight: 1.4,
        }}>
          {children}
        </span>
      )}
    </span>
  );
};

export default InfoTip;
