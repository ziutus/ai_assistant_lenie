import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import RadarSelectionMenu from "./radarSelectionMenu";

const renderMenu = () => render(
  <MemoryRouter>
    <RadarSelectionMenu apiUrl="http://api" headers={{ "x-api-key": "k" }} sourceContext="WhatsApp: Sąsiedzi">
      <p data-radar-context="Ala, dziś">Polecam narzędzie Obsidian do notatek</p>
    </RadarSelectionMenu>
  </MemoryRouter>,
);

const select = (text: string) => vi.spyOn(window, "getSelection").mockReturnValue({
  toString: () => text,
  get anchorNode() { return document.querySelector("p")?.firstChild ?? null; }, // the page is rendered after this call
} as unknown as Selection);

afterEach(() => { vi.restoreAllMocks(); });

describe("RadarSelectionMenu", () => {
  it("leaves the browser menu alone without a selection", () => {
    select("");
    renderMenu();
    const prevented = !fireEvent.contextMenu(screen.getByText(/Polecam/));
    expect(prevented).toBe(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("offers the selection and posts it to the radar with the chat as context", async () => {
    select("Obsidian");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ tool_recommendation: { id: 7, name: "Obsidian" } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderMenu();
    fireEvent.contextMenu(screen.getByText(/Polecam/));

    expect(screen.getByLabelText(/Nazwa narzędzia/)).toHaveProperty("value", "Obsidian");
    fireEvent.click(screen.getByText(/Dodaj do radaru$/));

    await waitFor(() => expect(screen.getByText(/Dodano/)).toBeTruthy());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api/tool_recommendations");
    expect(JSON.parse(init.body)).toEqual({
      name: "Obsidian", status: "watchlist", source_context: "WhatsApp: Sąsiedzi — Ala, dziś",
    });
  });

  it("says so when the name is already known", async () => {
    select("Obsidian");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ existing_tool: { id: 3, name: "Obsidian" } }),
    }));
    renderMenu();
    fireEvent.contextMenu(screen.getByText(/Polecam/));
    fireEvent.click(screen.getByText(/Dodaj do radaru$/));
    await waitFor(() => expect(screen.getByText(/jest już w katalogu/)).toBeTruthy());
  });
});
