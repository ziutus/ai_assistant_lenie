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

const renderFocus = (onDecide = vi.fn(), handlers: { onOpenPeer?: (id: number) => void; onChanged?: () => void } = {}, data: unknown = peers) => {
  const fetchMock = vi.fn(async () => ({ ok: true, json: async () => data }));
  vi.stubGlobal("fetch", fetchMock);
  render(<ToolFocusReview apiUrl="http://api" headers={{}} itemId={3} itemName="Clef" initialNote={null}
    position={1} total={2} busy={false} actions={[["compare", "Porównaj", "pomoc"], ["rejected", "Odrzuć", "pomoc"]]} currentStatus="watchlist" helpText="opis akcji"
    details={<p>opis Clefa</p>} onDecide={onDecide} onOpenPeer={handlers.onOpenPeer ?? vi.fn()}
    onChanged={handlers.onChanged ?? vi.fn()} onPrev={vi.fn()} onNext={vi.fn()} onClose={vi.fn()} />);
  return fetchMock;
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

  it("lets a neighbour from the category be decided or opened without leaving the card", async () => {
    const onOpenPeer = vi.fn();
    const onChanged = vi.fn();
    const fetchMock = renderFocus(vi.fn(), { onOpenPeer, onChanged });
    await screen.findByText("Jev");
    fireEvent.click(screen.getByRole("button", { name: "Jev: Odrzuć" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("http://api/tool_recommendations/1/status", expect.objectContaining({ method: "POST", body: JSON.stringify({ status: "rejected" }) }));
    expect(screen.queryByRole("button", { name: /Basal.*Odrzuć/ })).toBeNull();
    fireEvent.click(screen.getByTitle("Otwórz kartę Jev do pełnej oceny"));
    expect(onOpenPeer).toHaveBeenCalledWith(1);
  });

  it("moves the selected neighbours in one request and never the tool in use", async () => {
    const onChanged = vi.fn();
    const many = { ...peers, radar: [...peers.radar, { ...peers.radar[0], id: 4, name: "Backup A" }, { ...peers.radar[0], id: 5, name: "Backup B" }] };
    const fetchMock = renderFocus(vi.fn(), { onChanged }, many);
    await screen.findByText("Backup A");
    expect(screen.queryByRole("checkbox", { name: "Zaznacz Basal (Fabryka AI)" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Zaznacz wszystkie \(3\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Zaznaczone: Porównaj" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith("http://api/tool_recommendations/bulk_status", expect.objectContaining({ method: "POST", body: JSON.stringify({ ids: [1, 4, 5], status: "compare" }) }));
  });

  it("sends the note only when it was edited", async () => {
    const onDecide = vi.fn();
    renderFocus(onDecide);
    await screen.findByText("Jev");
    fireEvent.click(screen.getByRole("button", { name: /^Odrzuć/ }));
    expect(onDecide).toHaveBeenLastCalledWith("rejected", null);
    fireEvent.change(screen.getByLabelText(/Notatka do decyzji/), { target: { value: " wolniejszy od Basala " } });
    fireEvent.click(screen.getByRole("button", { name: /^Porównaj/ }));
    await waitFor(() => expect(onDecide).toHaveBeenLastCalledWith("compare", "wolniejszy od Basala"));
  });
});
