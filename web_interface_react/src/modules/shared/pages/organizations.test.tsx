import axios from "axios";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Organizations from "./organizations";

vi.mock("axios");
vi.mock("../context/authorizationContext", async () => {
  const { createContext } = await import("react");
  return { AuthorizationContext: createContext({ apiUrl: "", apiKey: "test-key" }) };
});

const WIKI = "https://pl.wikipedia.org/wiki/NATO";
const detail = {
  status: "success", id: 5, canonical_name: "NATO", organization_type: "organizacja międzynarodowa",
  description: "Sojusz wojskowy", headquarters_address: null, latitude: null, longitude: null, website: "https://www.nato.int",
  links: [{ url: WIKI, label: "Wikipedia" }, { url: "https://www.nato.int/cps", label: "" }],
  obsidian_note_path: null, primary_note_document_id: null, aliases: [], document_count: 0, ambiguous_with: [], note: null,
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/organizations/5")) return { data: detail };
    if (url.endsWith("/documents")) return { data: { documents: [] } };
    if (url.endsWith("/related")) return { data: { persons: [], places: [] } };
    if (url.endsWith("/countries")) return { data: { countries: [], suggestions: [] } };
    return { data: { entries: [], total: 0 } };
  });
});
afterEach(cleanup);

const open = () => render(
  <MemoryRouter initialEntries={["/organizations/5"]}>
    <Routes><Route path="/organizations/:id" element={<Organizations />} /></Routes>
  </MemoryRouter>,
);

it("shows the organization's external links, labelled by host when no label is stored", async () => {
  open();
  const links = await screen.findByTestId("organization-links");

  const anchors = Array.from(links.querySelectorAll("a"));
  expect(anchors.map((a) => a.getAttribute("href"))).toEqual([WIKI, "https://www.nato.int/cps"]);
  expect(anchors[0].textContent).toBe("Wikipedia");
  expect(anchors[1].textContent).toContain("nato.int");
  expect(anchors.every((a) => a.getAttribute("rel") === "noopener noreferrer")).toBe(true);
});

it("edits the links and sends only filled rows, trimmed, to PATCH /organizations/:id", async () => {
  vi.mocked(axios.patch).mockResolvedValue({ data: { ...detail, links: [{ url: "https://www.nato.int/cps", label: "Strona" }] } });
  open();
  await screen.findByTestId("organization-links");
  fireEvent.click(screen.getByRole("button", { name: /Edytuj/ }));

  // remove the Wikipedia row, label the second one, add an empty row that must be dropped
  fireEvent.click(screen.getAllByRole("button", { name: "Usuń link" })[0]);
  fireEvent.change(screen.getByLabelText("Etykieta linku 1"), { target: { value: " Strona " } });
  fireEvent.click(screen.getByRole("button", { name: "+ Dodaj link" }));
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/organizations/5",
    expect.objectContaining({ links: [{ url: "https://www.nato.int/cps", label: "Strona" }] }),
    expect.any(Object)));
  expect(await screen.findByText("Zapisano zmiany.")).toBeTruthy();
  const anchors = Array.from((await screen.findByTestId("organization-links")).querySelectorAll("a"));
  expect(anchors.map((a) => a.textContent)).toEqual(["Strona"]);
});
