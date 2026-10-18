import React from "react";
import { Link } from "react-router-dom";

// The channel / author (Document.byline) at the top of a document page. One channel has many
// documents and its own name glossary (/ner-glossary), so the name is a link to that glossary.
const ChannelBadge = ({ channel, style }: { channel?: string | null; style?: React.CSSProperties }) => {
  const name = (channel ?? "").trim();
  if (!name) return null;
  return (
    <Link
      to={`/ner-glossary?author=${encodeURIComponent(name)}`}
      title="Kanał / autor dokumentu — otwórz słownik nazw tego kanału"
      aria-label={`Kanał: ${name}`}
      style={{
        fontSize: "0.8em", fontWeight: 600, padding: "2px 9px", borderRadius: 10, textDecoration: "none",
        background: "#e0f2fe", color: "#075985", ...style,
      }}
    >
      📺 Kanał: {name}
    </Link>
  );
};

export default ChannelBadge;
