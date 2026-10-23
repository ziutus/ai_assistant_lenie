import React from "react";
import { hostOf, linksToText, textToLinks } from "../ToolCard/toolCardParts";

type LinkItem = { url: string; label: string };

/**
 * Every page about a radar entry: the homepage first, then the extra links (pricing, docs, a second repository…).
 * "Edytuj linki" opens one line per link (`address` or `Label | address`); nothing is sent until "Zapisz linki".
 */
export default function ToolLinksEditor({ homepageUrl, links, disabled, onSave }: {
  homepageUrl: string | null; links: LinkItem[]; disabled: boolean; onSave: (links: LinkItem[]) => void | Promise<void>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");
  const shown = [
    ...(homepageUrl ? [{ url: homepageUrl, label: "Strona narzędzia" }] : []),
    ...links.filter(link => link.url && link.url !== homepageUrl).map(link => ({ url: link.url, label: link.label || hostOf(link.url) })),
  ];

  const open = () => { setDraft(linksToText(links)); setEditing(true); };
  const save = async () => { await onSave(textToLinks(draft)); setEditing(false); };

  if (editing) {
    return <div style={{ margin: "6px 0" }}>
      <label style={{ display: "block", fontSize: ".85rem", color: "#475569" }}>
        Dodatkowe linki (jeden w wierszu: <code>adres</code> albo <code>Etykieta | adres</code>)
        <textarea rows={4} value={draft} disabled={disabled} onChange={event => setDraft(event.target.value)}
          placeholder={"Cennik | https://example.com/pricing\nhttps://gitlab.com/grupa/projekt"} style={{ width: "100%", display: "block", marginTop: 4 }} />
      </label>
      <div style={{ marginTop: 4, display: "flex", gap: 8 }}>
        <button type="button" disabled={disabled} onClick={() => void save()}>Zapisz linki</button>
        <button type="button" disabled={disabled} onClick={() => setEditing(false)}>Anuluj</button>
      </div>
    </div>;
  }
  return <div style={{ margin: "6px 0", display: "flex", flexWrap: "wrap", gap: "4px 12px", alignItems: "baseline" }}>
    {shown.map(link => <a key={link.url} href={link.url} target="_blank" rel="noreferrer" title={link.url}>{link.label}</a>)}
    <button type="button" disabled={disabled} onClick={open}
      title="Dodaj lub popraw dodatkowe linki: stronę z cennikiem, dokumentację, drugie repozytorium (GitHub i GitLab są liczone razem).">
      {links.length ? "✎ Edytuj linki" : "+ Dodaj linki"}
    </button>
  </div>;
}
