export interface ContactChannel {
  value: string;
  label: string | null;
}

interface Props {
  title: string;
  kind: "tel" | "email";
  entries: ContactChannel[];
  onChange: (entries: ContactChannel[]) => void;
}

export default function ContactChannelsEditor({ title, kind, entries, onChange }: Props) {
  const update = (index: number, patch: Partial<ContactChannel>) =>
    onChange(entries.map((entry, i) => i === index ? { ...entry, ...patch } : entry));

  return <fieldset style={{ gridColumn: "1 / -1", border: "1px solid #ddd", padding: 12 }}>
    <legend>{title}</legend>
    {entries.map((entry, index) => <div key={index} style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
      <label>
        {kind === "tel" ? "Numer" : "Adres"} {index + 1}{index === 0 ? " (główny)" : ""}
        <input type={kind} aria-label={`${title}: wartość ${index + 1}`} value={entry.value}
          maxLength={kind === "tel" ? 30 : 255} onChange={(e) => update(index, { value: e.target.value })} />
      </label>
      <label>
        Etykieta
        <input type="text" aria-label={`${title}: etykieta ${index + 1}`} value={entry.label ?? ""}
          placeholder="np. praca, dom" maxLength={100} onChange={(e) => update(index, { label: e.target.value || null })} />
      </label>
      {index > 0 && <button type="button" onClick={() => onChange([entry, ...entries.filter((_, i) => i !== index)])}>Ustaw jako główny</button>}
      <button type="button" aria-label={`${title}: usuń ${index + 1}`} onClick={() => onChange(entries.filter((_, i) => i !== index))}>Usuń</button>
    </div>)}
    <button type="button" disabled={entries.length >= 50} onClick={() => onChange([...entries, { value: "", label: null }])}>
      {kind === "tel" ? "Dodaj telefon" : "Dodaj adres e-mail"}
    </button>
  </fieldset>;
}
