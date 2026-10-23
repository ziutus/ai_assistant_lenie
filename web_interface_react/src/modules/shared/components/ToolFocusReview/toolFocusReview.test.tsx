import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ToolFocusReview from "./toolFocusReview";

const peers = {
  category: "DecisionModels",
  radar: [
    { id: 1, name: "Jev", status: "watchlist", category: "DecisionModels", description: "Model decyzyjny", homepage_url: null, personal_note: null, github: null },
    { id: 2, name: "Basal (Fabryka AI)", status: "adopted", category: "decision-models", description: null, homepage_url: "https://fabryka.ai/platform", personal_note: "działa", github: null },
  ],
  tools: [{ id: 9, name: "Zapier", homepage_url: null, personal_notes: null, pricing: null, license: null }],
};

const renderFocus = (onDecide = vi.fn()) => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => peers })));
  render(<ToolFocusReview apiUrl="http://api" headers={{}} itemId={3} itemName="Clef" initialNote={null}
    position={1} total={2} busy={false} actions={[["compare", "Porównaj", "pomoc"], ["rejected", "Odrzuć", "pomoc"]]}
    details={<p>opis Clefa</p>} onDecide={onDecide} onPrev={vi.fn()} onNext={vi.fn()} onClose={vi.fn()} />);
  return onDecide;
};

describe("ToolFocusReview", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("shows the candidate next to the tools already used, adopted first", async () => {
    renderFocus();
    await screen.findByText("Basal (Fabryka AI)");
    const names = screen.getAllByRole("region", { name: /Alternatywy/ })[0].querySelectorAll("strong");
    expect(Array.from(names).map(node => node.textContent)).toEqual(["Basal (Fabryka AI)", "Jev", "Zapier"]);
    expect(screen.getByText("opis Clefa")).toBeTruthy();
    expect(screen.getByText("W Spisie narzędzi")).toBeTruthy();
  });

  it("sends the note only when it was edited", async () => {
    const onDecide = renderFocus();
    await screen.findByText("Jev");
    fireEvent.click(screen.getByRole("button", { name: /^Odrzuć/ }));
    expect(onDecide).toHaveBeenLastCalledWith("rejected", null);
    fireEvent.change(screen.getByLabelText(/Notatka do decyzji/), { target: { value: " wolniejszy od Basala " } });
    fireEvent.click(screen.getByRole("button", { name: /^Porównaj/ }));
    await waitFor(() => expect(onDecide).toHaveBeenLastCalledWith("compare", "wolniejszy od Basala"));
  });
});
