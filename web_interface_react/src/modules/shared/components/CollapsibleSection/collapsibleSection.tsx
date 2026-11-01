import React from "react";

interface Props extends Omit<React.DetailsHTMLAttributes<HTMLDetailsElement>, "title"> {
  title: React.ReactNode;
  defaultOpen?: boolean;
  summaryExtra?: React.ReactNode;
}

const CollapsibleSection = React.forwardRef<HTMLDetailsElement, Props>(function CollapsibleSection(
  { title, defaultOpen = false, summaryExtra, children, style, open, onToggle, ...props }, ref,
) {
  const [localOpen, setLocalOpen] = React.useState(defaultOpen);
  return <details {...props} ref={ref} open={open ?? localOpen}
    onToggle={event => {
      if (event.target !== event.currentTarget) return;
      if (open === undefined) setLocalOpen(event.currentTarget.open);
      if (open === undefined || event.currentTarget.open !== open) onToggle?.(event);
    }}
    style={{ marginBottom: 14, padding: 12, border: "1px solid #cbd5e1", borderRadius: 6, background: "#f8fafc", ...style }}>
    <summary style={{ cursor: "pointer", fontWeight: "bold" }}>{title} {summaryExtra}</summary>
    {children}
  </details>;
});
export default CollapsibleSection;
