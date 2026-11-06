import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderMarkdown } from "../pages/read";
import {
  splitOutliersAroundKeys, STANCE_KEY, STANCE_OUTLIER, toneSpanStyle, toneSpanToNote, visibleToneSpans, type ToneSpan,
} from "./toneSpans";

const span = (over: Partial<ToneSpan> = {}): ToneSpan => ({
  id: 1, chapter_position: 2, role: "outlier", label: "złośliwy", quote: "Ale oczywiście, ekspert znów wie lepiej.",
  note: "docinek", importance: null, status: "proposed", model: "m", ...over,
});

describe("toneSpanToNote", () => {
  it("makes a synthetic note the reader's quote highlighter understands", () => {
    const note = toneSpanToNote(span({ status: "confirmed" }), 5);

    expect(note.id).toBeLessThan(0);
    expect(note.anchor_quote).toBe("Ale oczywiście, ekspert znów wie lepiej.");
    expect(note.stance).toBe(STANCE_OUTLIER);
    expect(note.note_text).toBe("złośliwy ✓ — docinek");
    expect(note.document_id).toBe(5);
  });

  it("marks a key passage with its own stance", () => {
    expect(toneSpanToNote(span({ role: "key", label: "kluczowy" }), 5).stance).toBe(STANCE_KEY);
  });
});

describe("visibleToneSpans", () => {
  const all = [
    span({ id: 1, chapter_position: 2 }),
    span({ id: 2, chapter_position: 3 }),
    span({ id: 3, chapter_position: null }),
    span({ id: 4, chapter_position: 2, status: "rejected" }),
  ];

  it("shows the chapter on screen and whole-document passages, never rejected ones", () => {
    expect(visibleToneSpans(all, 2, false).map((s) => s.id)).toEqual([1, 3]);
  });

  it("shows every chapter's passages in a compact reader", () => {
    expect(visibleToneSpans(all, 1, true).map((s) => s.id)).toEqual([1, 2, 3]);
  });
});

describe("toneSpanStyle", () => {
  it("is null for an ordinary note stance", () => {
    expect(toneSpanStyle("agree")).toBeNull();
    expect(toneSpanStyle(null)).toBeNull();
    expect(toneSpanStyle(STANCE_KEY)?.icon).toBe("⭐");
  });
});

describe("splitOutliersAroundKeys", () => {
  const outlier = { idx: 10, len: 100, kind: "note", note: { stance: STANCE_OUTLIER } };
  const key = { idx: 40, len: 30, kind: "note", note: { stance: STANCE_KEY } };

  it("cuts an outlier passage around the key sentence inside it", () => {
    const result = splitOutliersAroundKeys([outlier, key]);

    expect(result.map((m) => [m.idx, m.len, m.note?.stance])).toEqual([
      [10, 30, STANCE_OUTLIER],
      [40, 30, STANCE_KEY],
      [70, 40, STANCE_OUTLIER],
    ]);
  });

  it("drops an empty head or tail when the key sentence starts or ends the passage", () => {
    const atStart = splitOutliersAroundKeys([outlier, { ...key, idx: 10 }]);
    const atEnd = splitOutliersAroundKeys([outlier, { ...key, idx: 80 }]);

    expect(atStart.map((m) => [m.idx, m.len])).toEqual([[10, 30], [40, 70]]);
    expect(atEnd.map((m) => [m.idx, m.len])).toEqual([[10, 70], [80, 30]]);
  });

  it("leaves matches alone when no key sentence lies inside an outlier", () => {
    const outside = { ...key, idx: 200 };

    expect(splitOutliersAroundKeys([outlier, outside])).toEqual([outlier, outside]);
    expect(splitOutliersAroundKeys([outlier])).toEqual([outlier]);
  });
});

describe("the reader draws tone passages", () => {
  const SPITE = "Ale oczywiście, nasz wielki ekspert znów wie lepiej od wszystkich.";
  const KEY = "Problem polega na tym, że umowa przewiduje karę, której nikt nie wyegzekwuje.";
  const show = (text: string, notes: ReturnType<typeof toneSpanToNote>[]) =>
    render(<MemoryRouter><div>{renderMarkdown(text, notes)}</div></MemoryRouter>);

  it("marks an outlier red and a key sentence green, even when the key sentence sits inside the outlier", () => {
    const text = `Wstęp. ${SPITE} ${KEY} Koniec komentarza.`;
    const notes = [
      toneSpanToNote(span({ id: 1, quote: `${SPITE} ${KEY}` }), 5),
      toneSpanToNote(span({ id: 2, role: "key", label: "kluczowy", quote: KEY, note: "sedno" }), 5),
    ];

    const { container } = show(text, notes);

    const marks = Array.from(container.querySelectorAll("mark.tone-span-highlight"));
    expect(marks.map((m) => m.textContent)).toEqual([`${SPITE} `, KEY]);
    expect(marks[0].getAttribute("title")).toContain("⚠️");
    expect(marks[1].getAttribute("title")).toContain("⭐");
    expect((marks[0] as HTMLElement).style.background).not.toBe("");
    expect((marks[1] as HTMLElement).style.background).not.toBe((marks[0] as HTMLElement).style.background);
    expect(container.textContent).toBe(text);
  });

  it("tints the paragraph when the quote only matches after typography normalisation", () => {
    const text = "Powiedział „to jest absurd” i wyszedł z sali bez słowa wyjaśnienia.";
    const notes = [toneSpanToNote(span({ quote: 'Powiedział "to jest absurd" i wyszedł z sali' }), 5)];

    const { container } = show(text, notes);

    const paragraph = container.querySelector("p") as HTMLElement;
    expect(paragraph.getAttribute("title")).toContain("⚠️");
    expect(paragraph.style.borderLeft).toContain("3px solid");
  });
});
