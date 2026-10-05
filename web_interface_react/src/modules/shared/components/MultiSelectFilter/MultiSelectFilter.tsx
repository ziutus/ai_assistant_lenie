import React from "react";

interface Option {
  value: string;
  label: string;
}

interface MultiSelectFilterProps {
  options: Option[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  labels: { all: string; selected: string; heading: string };
  emptyOption?: Option;
  onTelemetry?: () => void;
  style?: React.CSSProperties;
  variant?: "select";
}

export default function MultiSelectFilter({
  options, selectedValues, onChange, labels, emptyOption, onTelemetry, style, variant,
}: MultiSelectFilterProps) {
  const filterRef = React.useRef<HTMLDetailsElement>(null);
  const allOptions = emptyOption ? [...options, emptyOption] : options;
  const allValues = allOptions.map(option => option.value);
  const allSelected = selectedValues.length === allValues.length
    && allValues.every(value => selectedValues.includes(value));

  React.useEffect(() => {
    const closeOnOutsideClick = (event: PointerEvent) => {
      const filter = filterRef.current;
      if (filter?.open && !filter.contains(event.target as Node)) filter.open = false;
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    return () => document.removeEventListener("pointerdown", closeOnOutsideClick);
  }, []);

  const change = (values: string[]) => {
    onTelemetry?.();
    onChange(values);
  };

  return (
    <details ref={filterRef} style={{ position: "relative", ...style }}>
      <summary className={variant === "select" ? "multi-select-native" : undefined}
        style={variant === "select" ? undefined : { cursor: "pointer", padding: "6px 10px", border: "1px solid #bbb", borderRadius: 3 }}>
        {allSelected ? labels.all : `${labels.selected}: wybrano ${selectedValues.length}`}
      </summary>
      <div style={{ position: "absolute", zIndex: 2, background: "white", border: "1px solid #bbb", borderRadius: 3, padding: 10, minWidth: 260, boxShadow: "0 2px 8px #0002" }}>
        <div style={{ fontSize: "0.85em", fontWeight: 600, marginBottom: 4 }}>{labels.heading}</div>
        <div style={{ display: "flex", gap: 6, marginBottom: 5 }}>
          <button type="button" className="button" onClick={() => change(allValues)}>Zaznacz wszystkie</button>
          <button type="button" className="button" onClick={() => change([])}>Odznacz wszystkie</button>
          <button type="button" className="button" onClick={() => change(allValues.filter(value => !selectedValues.includes(value)))}>Odwróć wybór</button>
        </div>
        {allOptions.map(option => (
          <div key={option.value} className="group-filter-row" style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6,
            ...(option === emptyOption ? { borderTop: "1px solid #ddd", marginTop: 8, paddingTop: 8 } : {}),
          }}>
            <label style={{ display: "block", whiteSpace: "nowrap" }}>
              <input type="checkbox" checked={selectedValues.includes(option.value)}
                onChange={event => change(event.target.checked
                  ? [...selectedValues, option.value]
                  : selectedValues.filter(value => value !== option.value))} /> {option.label}
            </label>
            <button type="button" className="group-filter-only button"
              aria-label={`Tylko ${option.label}`}
              style={{ padding: "1px 6px", fontSize: "0.8em" }}
              onClick={() => change([option.value])}>tylko</button>
          </div>
        ))}
      </div>
    </details>
  );
}
