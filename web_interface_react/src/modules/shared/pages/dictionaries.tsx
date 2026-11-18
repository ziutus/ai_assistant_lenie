import React from "react";
import { useSearchParams } from "react-router-dom";
import NerChannelGlossary from "./nerChannelGlossary";
import TranscriptCorrectionsTable from "../components/TranscriptCorrectionsTable/transcriptCorrectionsTable";

// One page for every name/phrase dictionary that repairs speech-to-text slips. Three layers, three effects:
//  - channel glossary: names expected on one channel, applied to a COPY of the text before NER (stored text untouched);
//  - region dictionary: rules bound to a country tag (kraj-*), rewriting the stored transcript;
//  - phrase rules: two-word-or-longer corrections, global or for one channel, rewriting the stored transcript.

type Tab = "channel" | "region" | "phrases";

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: "channel", label: "Kanał", hint: "nazwy oczekiwane na kanale; poprawiają kopię tekstu dla NER" },
  { id: "region", label: "Region", hint: "reguły dla kraju (tag kraj-*); poprawiają zapisany tekst" },
  { id: "phrases", label: "Frazy", hint: "frazy globalne lub dla kanału; poprawiają zapisany tekst" },
];

const Dictionaries = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const tab: Tab = TABS.some((item) => item.id === requested) ? (requested as Tab) : "channel";
  const select = (next: Tab) => {
    // Filters and pages belong to a tab, so a switch keeps only the channel the user was looking at.
    const params = new URLSearchParams();
    params.set("tab", next);
    const author = searchParams.get("author");
    if (author && next === "channel") params.set("author", author);
    setSearchParams(params);
  };

  return <div>
    <h2>Słowniki poprawek transkrypcji</h2>
    <p style={{ color: "#64748b", fontSize: "0.9em" }}>
      Trzy warstwy: <strong>kanał</strong> (poprawia kopię dla NER), <strong>region</strong> i <strong>frazy</strong>
      {" "}(poprawiają zapisany tekst). W przeglądzie NER dokumentu (<code>/ner/:id</code>) widać przy każdym rozdziale, co słownik zmienił.
    </p>
    <div role="tablist" aria-label="Słowniki" style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
      {TABS.map((item) => (
        <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} title={item.hint}
          onClick={() => select(item.id)}
          style={{ fontWeight: tab === item.id ? 700 : 400, borderBottom: tab === item.id ? "3px solid #0284c7" : "3px solid transparent" }}>
          {item.label}
        </button>
      ))}
    </div>
    <p style={{ color: "#64748b", fontSize: "0.85em", marginTop: 0 }}>{TABS.find((item) => item.id === tab)?.hint}</p>
    {tab === "channel" && <NerChannelGlossary />}
    {tab === "region" && <TranscriptCorrectionsTable mode="region" />}
    {tab === "phrases" && <TranscriptCorrectionsTable mode="phrases" />}
  </div>;
};

export default Dictionaries;
