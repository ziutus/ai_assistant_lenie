import React from "react";

interface MapTarget {
  formatted_address: string;
  latitude: number | null;
  longitude: number | null;
}

export interface MapLink {
  label: string;
  href: string;
}

/** External map / routing links. Coordinates win over the text query when the address is geocoded. */
export const buildMapLinks = (address: MapTarget): MapLink[] => {
  const q = encodeURIComponent(address.formatted_address);
  const hasCoords = address.latitude != null && address.longitude != null;
  const point = hasCoords ? `${address.latitude},${address.longitude}` : q;
  const links: MapLink[] = [
    { label: "Google Maps — pokaż miejsce", href: `https://www.google.com/maps/search/?api=1&query=${point}` },
    { label: "Google Maps — trasa dojazdu", href: `https://www.google.com/maps/dir/?api=1&destination=${point}` },
    hasCoords
      ? { label: "OpenStreetMap — pokaż miejsce",
        href: `https://www.openstreetmap.org/?mlat=${address.latitude}&mlon=${address.longitude}#map=18/${address.latitude}/${address.longitude}` }
      : { label: "OpenStreetMap — pokaż miejsce", href: `https://www.openstreetmap.org/search?query=${q}` },
  ];
  if (hasCoords) {
    links.push({ label: "OpenStreetMap — trasa dojazdu",
      href: `https://www.openstreetmap.org/directions?route=%3B${address.latitude}%2C${address.longitude}` });
  }
  links.push(
    { label: "Waze — nawiguj", href: `https://waze.com/ul?q=${hasCoords ? point : q}&navigate=yes` },
    { label: "Apple Maps — trasa dojazdu", href: `https://maps.apple.com/?daddr=${point}` },
  );
  return links;
};

interface Props {
  address: MapTarget;
  /** Inline map is offered only when the address has coordinates; otherwise the menu offers to geocode it. */
  inlineOpen: boolean;
  onToggleInline: () => void;
  onGeocode: () => void;
  busy?: boolean;
}

const AddressMapMenu: React.FC<Props> = ({ address, inlineOpen, onToggleInline, onGeocode, busy }) => {
  const ref = React.useRef<HTMLDetailsElement>(null);
  React.useEffect(() => {
    const close = (event: PointerEvent) => {
      const el = ref.current;
      if (el?.open && !el.contains(event.target as Node)) el.open = false;
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);

  const hasCoords = address.latitude != null && address.longitude != null;
  const closeMenu = () => { if (ref.current) ref.current.open = false; };
  const [active, setActive] = React.useState<string | null>(null);
  const itemProps = (key: string) => ({
    role: "menuitem" as const,
    style: {
      display: "block", padding: "6px 12px", textAlign: "left", border: 0, width: "100%", boxSizing: "border-box",
      cursor: "pointer", textDecoration: "none", color: "inherit", font: "inherit", whiteSpace: "nowrap",
      background: active === key ? "#dbeafe" : "none",
    } as React.CSSProperties,
    onMouseEnter: () => setActive(key),
    onMouseLeave: () => setActive(null),
    onFocus: () => setActive(key),
    onBlur: () => setActive(null),
  });
  const coordsTitle = hasCoords
    ? `Współrzędne: ${address.latitude!.toFixed(5)}, ${address.longitude!.toFixed(5)}`
    : "Adres bez współrzędnych";

  return (
    <details ref={ref} style={{ position: "relative", flexShrink: 0 }}>
      <summary className={"button"} title={coordsTitle}
        style={{ display: "inline-block", cursor: "pointer", whiteSpace: "nowrap" }}>🗺 Mapa ▾</summary>
      <div role="menu" style={{ position: "absolute", right: 0, zIndex: 10, background: "#fff",
        border: "1px solid #ccc", borderRadius: 6, minWidth: 260, marginTop: 2, overflow: "hidden",
        boxShadow: "0 2px 8px rgba(0,0,0,.15)" }}>
        {hasCoords
          ? <button type="button" {...itemProps("inline")} onClick={() => { onToggleInline(); closeMenu(); }}>
            {inlineOpen ? "🗺 Ukryj mapę poniżej" : "🗺 Pokaż mapę poniżej"}
          </button>
          : <button type="button" {...itemProps("inline")} disabled={busy}
            onClick={() => { onGeocode(); closeMenu(); }}>📍 Geokoduj i pokaż mapę poniżej</button>}
        {buildMapLinks(address).map(link => (
          <a key={link.label} {...itemProps(link.label)} href={link.href} target="_blank" rel="noopener noreferrer"
            onClick={closeMenu}>{link.label}</a>
        ))}
      </div>
    </details>
  );
};

export default AddressMapMenu;
