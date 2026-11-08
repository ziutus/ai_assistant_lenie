import axios from "axios";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import EntitiesPanel, { EntityChips } from "./entitiesPanel";

vi.mock("axios");
afterEach(cleanup);
const place = { id: 7, text: "Jemenu Północnego", count: 2 };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [place], placeName: [{ id: 8, text: "Aden", count: 1 }] } } }));
  vi.mocked(axios.patch).mockResolvedValue({ data: {} });
});
const openMenu = async () => {
  await screen.findByRole("button", { name: place.text });
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: place.text }));
};

const clickRetype = (label: string) => {
  fireEvent.click(screen.getByRole("menuitem", { name: /^Zmień na…/ }));
  fireEvent.click(screen.getByRole("menuitem", { name: label }));
};

it("keeps country history with hidden country chips and refreshes after detection", async () => {
  vi.mocked(axios.get).mockImplementation(async url => ({ data: url.includes("country_detections")
    ? { detections: [] } : url.endsWith("enrichment_job") ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [], placeName: [] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: { countries: [], added: [], detection_id: 99 } });
  render(<MemoryRouter><EntitiesPanel docId={10753} hideCountriesRow /></MemoryRouter>);
  const historyCalls = () => vi.mocked(axios.get).mock.calls.filter(([url]) => url.includes("country_detections"));
  expect(historyCalls()).toHaveLength(0);
  fireEvent.click(screen.getByText("Dlaczego te państwa? (historia wykrywania)"));
  await screen.findByText("Brak zapisanej historii wykrywania państw dla tego dokumentu.");
  expect(historyCalls()).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Wykryj państwa" }));
  await waitFor(() => expect(historyCalls()).toHaveLength(2));
});

it("shows the full proposal and confirms it without edit mode", async () => {
  const proposed = { id: 7, text: "Huty", count: 4, verified: false, place_verification_status: "needs_review",
    proposed_geocode_id: 17, proposed_display_name: "Huti, obwód lwowski, Ukraina", proposed_lat: 49, proposed_lon: 24 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [], orgName: [], geogName: [proposed], placeName: [] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  expect(await screen.findByText(/Wymaga potwierdzenia/)).toBeTruthy();
  expect(screen.getByText("Propozycja lokalizacji: Huti, obwód lwowski, Ukraina")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź tę lokalizację" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/7/confirm_place",
    { selected_geocode_id: 17 }, { headers: expect.any(Object) }));
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(3));
});

it("rejects a location proposal without editing the name", async () => {
  const proposed = { id: 7, text: "Huty", count: 4, verified: false, place_verification_status: "needs_review",
    proposed_geocode_id: 17, proposed_display_name: "Huti, obwód lwowski, Ukraina", proposed_lat: 49, proposed_lon: 24 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [], orgName: [], geogName: [proposed], placeName: [] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "Odrzuć propozycję" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/7/reject_place",
    {}, { headers: expect.any(Object) }));
  expect(await screen.findByText(/Propozycja lokalizacji dla „Huty” odrzucona/)).toBeTruthy();
});

it("changes a place into an organization from the menu", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", organization_name: "Huti" } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  clickRetype("Organizacja");
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/7/to_organization",
    {}, { headers: expect.any(Object) }));
  expect(await screen.findByText(/zmienione na organizację: Huti/)).toBeTruthy();
});

it("renames a place without edit mode and refetches entities", async () => {
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  expect(screen.getAllByRole("menuitem")).toHaveLength(12);
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  const input = screen.getByRole("textbox", { name: "Popraw nazwę miejsca" });
  expect((input as HTMLInputElement).value).toBe(place.text);
  fireEvent.change(input, { target: { value: " Jemen Północny " } });
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/website_entities/7",
    { text: "Jemen Północny" }, { headers: expect.objectContaining({ "Content-Type": "application/json" }) }));
  expect(await screen.findByText("Nazwa miejsca została poprawiona — geokoder nie potwierdził.")).toBeTruthy();
  expect(axios.get).toHaveBeenCalledTimes(3);
});

it("draws chapter-scoped groups through the panel's own menus in chapter mode", async () => {
  render(<MemoryRouter><EntitiesPanel docId={10753} chapterRenderer={(renderGroups) => (
    <div data-testid="chapter">{renderGroups({ placeName: [{ id: 8, text: "Aden", count: 1 }] })}</div>
  )} /></MemoryRouter>);
  const chapter = await screen.findByTestId("chapter");
  await act(async () => {});
  expect(within(chapter).getByRole("button", { name: "Aden" })).toBeTruthy();
  // The document-level groups are replaced, so the other place of the document is not drawn.
  expect(screen.queryByRole("button", { name: place.text })).toBeNull();
  fireEvent.click(within(chapter).getByRole("button", { name: "Aden" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  expect((screen.getByRole("textbox", { name: "Popraw nazwę miejsca" }) as HTMLInputElement).value).toBe("Aden");
});

it.each([false, true])("offers merge after rename (conflict: %s)", async (conflict) => {
  const target = { id: 8, text: "Aden", entity_type: "placeName" };
  if (conflict) {
    vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: { conflict_entity: target } } });
  } else {
    vi.mocked(axios.patch).mockResolvedValue({ data: { geocoded: true, same_place_entity: target } });
  }
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  // "Adenn" is not in the document's list, so only the server (409 / same geocode) knows it is Aden.
  fireEvent.change(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" }), { target: { value: "Adenn" } });
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
  expect(await screen.findByText(conflict
    ? "Miejsce „Aden” już istnieje — połączyć?" : "To samo miejsce co „Aden” — połączyć?")).toBeTruthy();
  if (!conflict) expect(screen.getByText(/miejsce potwierdzone przez geokoder/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Połącz" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/document/10753/places/merge",
    { source_entity_id: 7, target_entity_id: 8 }, { headers: expect.any(Object) }));
  expect(await screen.findByText("Miejsca zostały połączone.")).toBeTruthy();
  expect(axios.get).toHaveBeenCalledTimes(conflict ? 3 : 4);
  expect(screen.queryByRole("button", { name: "Połącz" })).toBeNull();
});

it("turns the rename into a merge when the typed name is another place of the document", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  expect(screen.getByRole("checkbox")).toBeTruthy();
  fireEvent.change(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" }), { target: { value: " aden " } });
  expect(screen.getByText(/To samo miejsce co „Aden”/)).toBeTruthy();
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(screen.queryByRole("button", { name: "Zatwierdź" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Połącz z „Aden”" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/document/10753/places/merge",
    { source_entity_id: 7, target_entity_id: 8 }, { headers: expect.any(Object) }));
  expect(axios.patch).not.toHaveBeenCalled();
  expect(await screen.findByText("Miejsca zostały połączone.")).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
});

it("shows a backend conflict and keeps the form open", async () => {
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: { message: "Wybierz „Połącz z innym miejscem”." } } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
  expect(await screen.findByText("Wybierz „Połącz z innym miejscem”.")).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeTruthy();
});

it("reloads the list and closes the form when the renamed entity no longer exists", async () => {
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 404, data: { message: "Nie znaleziono encji." } } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
  expect(await screen.findByText(/Ta encja już nie istnieje/)).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
  expect(axios.get).toHaveBeenCalledTimes(3);
});

it.each(["× Usuń encję", "🚫 Usuń i nie wykrywaj więcej", "Połącz z innym miejscem"])(
  "opens the existing %s flow without edit mode", async (action) => {
    render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
    await openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: action }));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("button", { name: "Edytuj" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "✕ anuluj" })).toBeTruthy();
    if (action !== "Połącz z innym miejscem") expect(screen.getByRole("combobox")).toBeTruthy();
  },
);

it("closes on outside pointerdown and Escape, and clears rename on document change", async () => {
  const view = render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole("menu")).toBeNull();
  await openMenu();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  view.rerender(<MemoryRouter><EntitiesPanel docId={10754} /></MemoryRouter>);
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
});

it("refetches and clears open forms when refreshKey changes for the same document", async () => {
  const view = render(<MemoryRouter><EntitiesPanel docId={10753} refreshKey={0} /></MemoryRouter>);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  expect(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeTruthy();
  const callsBefore = vi.mocked(axios.get).mock.calls.length;
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [], placeName: [] } } }));
  view.rerender(<MemoryRouter><EntitiesPanel docId={10753} refreshKey={1} /></MemoryRouter>);
  await waitFor(() => expect(vi.mocked(axios.get).mock.calls.length).toBe(callsBefore + 2));
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
  expect(screen.queryByRole("button", { name: place.text })).toBeNull();
});

const emptyEntities = { persName: [], orgName: [], geogName: [], placeName: [] };

it("does not announce completion for a stale finished job it never saw running", async () => {
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: { id: "old", status: "done", progress: null } }
    : { entities: emptyEntities } }));
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
  await act(async () => {});
  expect(screen.queryByText(/Pełna weryfikacja encji zakończona/)).toBeNull();
});

it("announces completion after watching a job go from running to done", async () => {
  let jobCalls = 0;
  vi.mocked(axios.get).mockImplementation(async (url) => {
    if (!url.endsWith("enrichment_job")) return { data: { entities: emptyEntities } };
    jobCalls += 1;
    return { data: { job: { id: "j", status: jobCalls === 1 ? "running" : "done", progress: null } } };
  });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  expect(await screen.findByText("Pełna weryfikacja encji zakończona.", {}, { timeout: 6000 })).toBeTruthy();
}, 10000);

it("shows read-only place tags under Miejsca only when the document has them", async () => {
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [place], placeName: [] },
      place_tags: ["miejsce-aden", "miejsce-rijad"] } }));
  const view = render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  expect(await screen.findByText("Tagi miejsc: miejsce-aden, miejsce-rijad")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Czym są tagi miejsc" }));
  expect(screen.getByRole("note").textContent).toContain("nie ma osobnego filtra po tagach");
  view.unmount();

  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [place], placeName: [] } } }));
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await screen.findByRole("button", { name: place.text });
  expect(screen.queryByText(/Tagi miejsc:/)).toBeNull();
});

// ── Cited sources / organizations: rename + source details ─────────────────────────
const citedOrg = {
  id: 11, text: "telegrapha", count: 1, organization_id: 842, information_source_id: 200,
  information_source_name: "telegrapha", information_source_type: "organization",
  information_source_domain: null, information_source_description: null, organization_description: null,
};
const mockOrgEntities = (org: Record<string, unknown> = citedOrg) => {
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [org], geogName: [], placeName: [] } } }));
};
const renderInRouter = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);
const openOrgMenu = async (name = "telegrapha") => {
  await screen.findByRole("button", { name });
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name }));
};

it("offers the organization menu on a cited source, including a link to the sources registry", async () => {
  mockOrgEntities();
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu();

  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
    "Kopiuj nazwę", "Szukaj w Google", "Otwórz w rejestrze źródeł", "Popraw nazwę", "Dane źródła (typ, strona, opis)",
    "Połącz z inną organizacją", "Dodaj stronę Wikipedii", "Podziel na kilka organizacji…", "To błąd transkrypcji…", "Zmień na… ▸",
    "× Usuń encję", "🚫 Usuń i nie wykrywaj więcej",
  ]);
  expect(screen.getByRole("menuitem", { name: "Otwórz w rejestrze źródeł" }).getAttribute("href"))
    .toBe("/information-sources?id=200");
});

it("renames an organization globally and reports the merged source", async () => {
  mockOrgEntities();
  vi.mocked(axios.patch).mockResolvedValue({ data: {
    canonical_name: "The Telegraph",
    rename: { old_name: "telegrapha", source: { action: "merged", source_id: 75 } },
  } });
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  const input = screen.getByRole("textbox", { name: /Popraw nazwę organizacji/ });
  expect((input as HTMLInputElement).value).toBe("telegrapha");
  fireEvent.change(input, { target: { value: " The Telegraph " } });
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));

  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/organizations/842",
    { canonical_name: "The Telegraph" }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/Nazwa organizacji poprawiona: „telegrapha” → „The Telegraph”\. Źródło scalono/))
    .toBeTruthy();
  expect(axios.patch).not.toHaveBeenCalledWith(expect.stringContaining("/website_entities/"), expect.anything(), expect.anything());
  expect(axios.get).toHaveBeenCalledTimes(3);
});

it("shows the backend conflict when the corrected organization name is taken", async () => {
  mockOrgEntities();
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: { message: "Nazwa zajęta." } } });
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));

  expect(await screen.findByText("Nazwa zajęta. Użyj „Połącz z inną organizacją”.")).toBeTruthy();
});

const mergePreviewPayload = {
  status: "success",
  source: {
    id: 842, canonical_name: "telegrapha", organization_type: null, description: null, aliases: [],
    document_count: 3,
    information_source: { id: 200, canonical_name: "telegrapha", source_type: "organization", domain: null,
      description: null, document_count: 3 },
  },
  target: {
    id: 281, canonical_name: "Zjednoczone Emiraty Arabskie", organization_type: "country", description: "Państwo w Azji",
    aliases: ["ZEA"], document_count: 12,
    information_source: { id: 75, canonical_name: "Zjednoczone Emiraty Arabskie", source_type: "country",
      domain: "government.ae", description: null, document_count: 9 },
  },
  effects: {
    alias_added: "telegrapha", aliases_moved: [], documents_moved: 2, documents_in_both: 1, entities_renamed: 3,
    source_action: "merge_sources", source_fields_dropped: ["source_type"],
  },
};
const mockOrgEntitiesWithPreview = () => {
  vi.mocked(axios.get).mockImplementation(async (url) => {
    if (url.endsWith("enrichment_job")) return { data: { job: null } };
    if (url.endsWith("/merge_preview")) return { data: mergePreviewPayload };
    if (url.endsWith("/organizations")) {
      return { data: { entries: [{ id: 281, canonical_name: "Zjednoczone Emiraty Arabskie", aliases: ["ZEA"], document_count: 12 }] } };
    }
    return { data: { entities: { persName: [], orgName: [citedOrg], geogName: [], placeName: [] } } };
  });
};

it("turns a taken organization name into a merge with a side-by-side preview and a Połącz button", async () => {
  mockOrgEntitiesWithPreview();
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: {
    message: "alias 'Zjednoczone Emiraty Arabskie' already belongs to organization 281", existing_organization_id: 281,
  } } });
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.change(screen.getByRole("textbox", { name: /Popraw nazwę organizacji/ }),
    { target: { value: "Zjednoczone Emiraty Arabskie" } });
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));

  expect(await screen.findByText("Łączona (zniknie)")).toBeTruthy();
  expect(axios.get).toHaveBeenCalledWith("/organizations/842/merge_preview",
    { params: { target_id: 281 }, headers: expect.any(Object) });
  expect(screen.getByText("Państwo w Azji")).toBeTruthy();
  expect(screen.getByText(/2 dok\. zostanie powiązanych/)).toBeTruthy();
  expect(screen.getByText(/1 dok\. ma obie organizacje/)).toBeTruthy();
  expect(screen.getByText(/3 encji w dokumentach zmieni nazwę/)).toBeTruthy();
  expect(screen.getByText(/Utracone dane źródła \(cel ma własne\): typ/)).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: /Popraw nazwę organizacji/ })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Połącz" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/document/10753/organizations/merge",
    { source_entity_id: 11, target_organization_id: 281, make_global_alias: true }, { headers: expect.any(Object) }));
  expect(await screen.findByText("Połączono organizacje: „telegrapha” → „Zjednoczone Emiraty Arabskie”.")).toBeTruthy();
  expect(screen.queryByText("Łączona (zniknie)")).toBeNull();
});

it("shows the comparison before a registry merge and does nothing on Anuluj", async () => {
  mockOrgEntitiesWithPreview();
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Połącz z inną organizacją" }));
  fireEvent.change(screen.getByPlaceholderText("Nazwa organizacji…"), { target: { value: "Emirat" } });
  await screen.findByText("ZEA", { exact: false });
  fireEvent.click(screen.getAllByRole("button", { name: "wybierz" })[0]);

  expect(await screen.findByText("Łączona (zniknie)")).toBeTruthy();
  expect(axios.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Anuluj" }));
  expect(screen.queryByText("Łączona (zniknie)")).toBeNull();
  expect(axios.post).not.toHaveBeenCalled();
});

it("reports a failed preview instead of merging blind", async () => {
  vi.mocked(axios.get).mockImplementation(async (url) => {
    if (url.endsWith("enrichment_job")) return { data: { job: null } };
    if (url.endsWith("/merge_preview")) throw { response: { status: 404, data: { message: "Organization not found" } } };
    return { data: { entities: { persName: [], orgName: [citedOrg], geogName: [], placeName: [] } } };
  });
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: { existing_organization_id: 281 } } });
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));

  expect(await screen.findByText(/Organization not found/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Połącz" })).toBeNull();
  expect(axios.post).not.toHaveBeenCalled();
});

it("saves source type, website and description from 'Dane źródła'", async () => {
  mockOrgEntities({ ...citedOrg, organization_description: "stary opis" });
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Dane źródła (typ, strona, opis)" }));

  expect((screen.getByLabelText(/Typ źródła/) as HTMLInputElement).value).toBe("organization");
  expect((screen.getByLabelText(/Opis \(np\./) as HTMLTextAreaElement).value).toBe("stary opis");
  fireEvent.change(screen.getByLabelText(/Typ źródła/), { target: { value: " newspaper " } });
  fireEvent.change(screen.getByLabelText(/Strona/), { target: { value: "https://www.telegraph.co.uk/" } });
  fireEvent.change(screen.getByLabelText(/Opis \(np\./), { target: { value: "Brytyjski dziennik, 1855" } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

  await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/information_sources/200", {
    source_type: "newspaper", domain: "https://www.telegraph.co.uk/", description: "Brytyjski dziennik, 1855",
  }, { headers: expect.any(Object) }));
  expect(await screen.findByText("Dane źródła zapisane.")).toBeTruthy();
});

it("shows the backend validation message for bad source details and keeps the form", async () => {
  mockOrgEntities();
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 400, data: { message: "domain must be a host name" } } });
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Dane źródła (typ, strona, opis)" }));
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

  expect(await screen.findByText("domain must be a host name")).toBeTruthy();
  expect(screen.getByLabelText(/Strona/)).toBeTruthy();
});

it("uses type, website and description as the cited source tooltip", async () => {
  mockOrgEntities({
    ...citedOrg, text: "The Telegraph", information_source_type: "newspaper",
    information_source_domain: "telegraph.co.uk", information_source_description: "Brytyjski dziennik, 1855",
  });
  renderInRouter(<EntitiesPanel docId={10753} />);
  const chip = (await screen.findByRole("button", { name: "The Telegraph" })).parentElement as HTMLElement;

  expect(chip.getAttribute("title")).toBe("newspaper · telegraph.co.uk · Brytyjski dziennik, 1855");
});

it("an organization that is not a source gets 'Opis organizacji' and the registry link", async () => {
  mockOrgEntities({ id: 12, text: "ONZ", count: 3, organization_id: 5, organization_description: null });
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu("ONZ");

  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
    "Kopiuj nazwę", "Szukaj w Google", "Otwórz w rejestrze organizacji", "Popraw nazwę", "Opis organizacji",
    "Połącz z inną organizacją", "Dodaj stronę Wikipedii", "Podziel na kilka organizacji…", "To błąd transkrypcji…", "Zmień na… ▸",
    "× Usuń encję", "🚫 Usuń i nie wykrywaj więcej",
  ]);
  fireEvent.click(screen.getByRole("menuitem", { name: "Opis organizacji" }));
  expect(screen.getByText(/Krótki opis dla:/)).toBeTruthy();
});

describe("Wikipedia article of an organization (stored in its links list)", () => {
  const nato = {
    id: 12, text: "NATO", count: 3, organization_id: 5,
    organization_links: [{ url: "https://www.nato.int", label: "Strona" }],
  };
  const openWikiForm = async (org: Record<string, unknown>) => {
    mockOrgEntities(org);
    vi.mocked(axios.patch).mockResolvedValue({ data: { status: "success" } });
    renderInRouter(<EntitiesPanel docId={10753} />);
    await openOrgMenu("NATO");
  };

  it("adds the article and keeps the other links of the organization", async () => {
    await openWikiForm(nato);
    fireEvent.click(screen.getByRole("menuitem", { name: "Dodaj stronę Wikipedii" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: " https://pl.wikipedia.org/wiki/NATO " } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/organizations/5",
      { links: [{ url: "https://pl.wikipedia.org/wiki/NATO", label: "Wikipedia" },
        { url: "https://www.nato.int", label: "Strona" }] }, { headers: expect.any(Object) }));
    expect(await screen.findByText(/Zapisano artykuł Wikipedii/)).toBeTruthy();
    expect(axios.put).not.toHaveBeenCalled();
  });

  it("replaces only the Wikipedia entry and removes it on an empty address", async () => {
    const withWiki = { ...nato, wikipedia_url: "https://pl.wikipedia.org/wiki/NATO",
      organization_links: [{ url: "https://pl.wikipedia.org/wiki/NATO", label: "Wikipedia" }, ...nato.organization_links] };
    await openWikiForm(withWiki);
    expect(await screen.findByRole("link", { name: "Wikipedia: NATO" })).toBeTruthy();
    fireEvent.click(screen.getByRole("menuitem", { name: "Zmień stronę Wikipedii" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith("/organizations/5",
      { links: [{ url: "https://www.nato.int", label: "Strona" }] }, { headers: expect.any(Object) }));
    expect(await screen.findByText(/Usunięto link Wikipedii/)).toBeTruthy();
  });

  it("refuses an address that is not a Wikipedia article without calling the API", async () => {
    await openWikiForm(nato);
    fireEvent.click(screen.getByRole("menuitem", { name: "Dodaj stronę Wikipedii" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "https://wikipedia.org.evil.example/wiki/NATO" } });
    fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));

    expect(await screen.findByText(/musi być artykułem Wikipedii/)).toBeTruthy();
    expect(axios.patch).not.toHaveBeenCalled();
  });
});

it("changes a mis-tagged organization into a place with an editable name", async () => {
  mockOrgEntities({ id: 16615, text: "Tela Avivwu", count: 1, organization_id: 1140 });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", place_name: "Tel Awiw" } });
  renderInRouter(<EntitiesPanel docId={10872} />);
  await openOrgMenu("Tela Avivwu");
  clickRetype("Miejsce");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Tel Awiw" } });
  fireEvent.click(screen.getByRole("button", { name: "Zmień na miejsce" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/16615/to_place",
    { text: "Tel Awiw" }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/zmienione na miejsce: Tel Awiw/)).toBeTruthy();
});

const renderManualChips = (props: Record<string, unknown> = {}) => {
  mockOrgEntities();
  renderInRouter(<EntitiesPanel docId={11143} {...props} chapterRenderer={(renderGroups) => <>{renderGroups({
    productName: [{ id: 78, text: "Starlink", count: 3 }],
    eventName: [{ id: 77, text: "Szczyt NATO", count: 1, description: null }],
  })}</>} />);
};

it("gives product chips the shared dropdown menu with retype, merge, highlight and delete", async () => {
  const onMergeProducts = vi.fn();
  const onShowInText = vi.fn();
  renderManualChips({ onMergeProducts, onShowInText });
  await openOrgMenu("Starlink");
  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
    "Kopiuj nazwę", "Szukaj w Google", "🔎 Podświetl w tekście", "Otwórz stronę produktu", "Scal z innymi zapisami…", "Zmień na… ▸", "× Usuń encję",
  ]);
  fireEvent.click(screen.getByRole("menuitem", { name: "Scal z innymi zapisami…" }));
  expect(onMergeProducts).toHaveBeenCalledWith(expect.objectContaining({ id: 78 }));
  await openOrgMenu("Starlink");
  fireEvent.click(screen.getByRole("menuitem", { name: "🔎 Podświetl w tekście" }));
  expect(onShowInText).toHaveBeenCalledWith(expect.objectContaining({ id: 78 }), "product");
});

it("shows retype targets in order without the product's own type", async () => {
  renderManualChips();
  await openOrgMenu("Starlink");
  const parent = screen.getByRole("menuitem", { name: /^Zmień na…/ });
  const topLevel = screen.getAllByRole("menuitem");
  expect(parent.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(parent);
  expect(parent.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getAllByRole("menuitem").filter((item) => !topLevel.includes(item))
    .map((item) => item.textContent)).toEqual(["Osoba", "Organizacja", "Miejsce", "Wydarzenie", "Pojęcie"]);
  expect(screen.queryByRole("menuitem", { name: "Produkt / system" })).toBeNull();
});

it("turns a product back into a place from its menu", async () => {
  renderManualChips();
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  await openOrgMenu("Starlink");
  clickRetype("Miejsce");
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/78/from_product",
    { entity_type: "placeName" }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/zmienione na miejsce/)).toBeTruthy();
});

it("gives event chips the shared menu: description, retype to product, delete", async () => {
  const onDescribeEvent = vi.fn();
  renderManualChips({ onDescribeEvent });
  await openOrgMenu("Szczyt NATO");
  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
    "Kopiuj nazwę", "Szukaj w Google", "Dodaj opis wydarzenia…", "Zmień na… ▸", "× Usuń encję",
  ]);
  fireEvent.click(screen.getByRole("menuitem", { name: "Dodaj opis wydarzenia…" }));
  expect(onDescribeEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 77 }));
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  await openOrgMenu("Szczyt NATO");
  clickRetype("Produkt / system");
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/77/from_product",
    { entity_type: "productName" }, { headers: expect.any(Object) }));
});

it("offers promotion of an event name to the registry only when the page can open the dialog", async () => {
  const onLinkEvent = vi.fn();
  renderManualChips({ onLinkEvent });
  await openOrgMenu("Szczyt NATO");
  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
    "Kopiuj nazwę", "Szukaj w Google", "Dodaj do rejestru wydarzeń…", "Zmień na… ▸", "× Usuń encję",
  ]);
  fireEvent.click(screen.getByRole("menuitem", { name: "Dodaj do rejestru wydarzeń…" }));
  expect(onLinkEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 77, text: "Szczyt NATO" }));
});

const renderLinkedEvent = (props: Record<string, unknown> = {}) => {
  mockOrgEntities();
  renderInRouter(<EntitiesPanel docId={11237} {...props} chapterRenderer={(renderGroups) => <>{renderGroups({
    eventName: [{ id: 77, text: "Konwencja Demokratów", count: 1, description: null,
      registry_event: { id: 68, title: "Krajowa Konwencja Demokratów 2024 (Chicago)", status: "confirmed",
        surface: "Konwencja Demokratów" } }],
  })}</>} />);
};

it("marks an event name that is linked to a registry event and offers open / change / unlink", async () => {
  const onLinkEvent = vi.fn();
  renderLinkedEvent({ onLinkEvent });
  expect(screen.getByTitle("W rejestrze wydarzeń: #68 Krajowa Konwencja Demokratów 2024 (Chicago)")).toBeTruthy();
  await openOrgMenu("Konwencja Demokratów");
  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
    "Kopiuj nazwę", "Szukaj w Google", "🔗 W rejestrze: #68 Krajowa Konwencja Demokratów 2024 (Chicago)", "Zmień powiązanie z rejestrem…",
    "Odłącz od wydarzenia z rejestru", "Zmień na… ▸", "× Usuń encję",
  ]);
  const open = screen.getByRole("menuitem", { name: /W rejestrze: #68/ });
  expect(open.getAttribute("href")).toBe("/world-events?q=" + encodeURIComponent("Krajowa Konwencja Demokratów 2024 (Chicago)"));
  fireEvent.click(screen.getByRole("menuitem", { name: "Zmień powiązanie z rejestrem…" }));
  expect(onLinkEvent).toHaveBeenCalledWith(expect.objectContaining({ id: 77 }));
});

it("unlinks an event name from the registry for this document only", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  renderLinkedEvent();
  await openOrgMenu("Konwencja Demokratów");
  fireEvent.click(screen.getByRole("menuitem", { name: "Odłącz od wydarzenia z rejestru" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/world_events/mentions/unlink",
    { name: "Konwencja Demokratów", event_id: 68, document_id: 11237 }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/odłączone od wydarzenia #68/)).toBeTruthy();
});

const renderConcept = (props: Record<string, unknown> = {}, linked = false) => {
  mockOrgEntities();
  renderInRouter(<EntitiesPanel docId={11239} {...props} chapterRenderer={(renderGroups) => <>{renderGroups({
    conceptName: [{ id: 90, text: "Ciemne oświecenie", count: 4,
      ...(linked ? { registry_concept: { id: 5, name: "Ciemne oświecenie", surface: "Ciemne oświecenie" } } : {}) }],
  })}</>} />);
};

it("gives concept chips a menu: registry promotion, retype to the other manual kinds, delete", async () => {
  const onLinkConcept = vi.fn();
  const onShowInText = vi.fn();
  renderConcept({ onLinkConcept, onShowInText });
  expect(screen.getByText(/Pojęcia i ideologie/)).toBeTruthy();
  await openOrgMenu("Ciemne oświecenie");
  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
    "Kopiuj nazwę", "Szukaj w Google", "🔎 Podświetl w tekście", "Dodaj do rejestru pojęć…", "Zmień na… ▸", "× Usuń encję",
  ]);
  fireEvent.click(screen.getByRole("menuitem", { name: "Dodaj do rejestru pojęć…" }));
  expect(onLinkConcept).toHaveBeenCalledWith(expect.objectContaining({ id: 90, text: "Ciemne oświecenie" }));
  await openOrgMenu("Ciemne oświecenie");
  fireEvent.click(screen.getByRole("menuitem", { name: "🔎 Podświetl w tekście" }));
  expect(onShowInText).toHaveBeenCalledWith(expect.objectContaining({ id: 90 }), "concept");
});

it("marks a concept linked to the registry and offers open / change / unlink", async () => {
  const onLinkConcept = vi.fn();
  renderConcept({ onLinkConcept }, true);
  expect(screen.getByTitle("W rejestrze pojęć: #5 Ciemne oświecenie")).toBeTruthy();
  await openOrgMenu("Ciemne oświecenie");
  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
    "Kopiuj nazwę", "Szukaj w Google", "🔗 W rejestrze: #5 Ciemne oświecenie", "Zmień powiązanie z rejestrem…",
    "Odłącz od pojęcia z rejestru", "Zmień na… ▸", "× Usuń encję",
  ]);
  expect(screen.getByRole("menuitem", { name: /W rejestrze: #5/ }).getAttribute("href")).toBe("/concepts?id=5");
});

it("unlinks a concept name from the registry for this document only", async () => {
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  renderConcept({}, true);
  await openOrgMenu("Ciemne oświecenie");
  fireEvent.click(screen.getByRole("menuitem", { name: "Odłącz od pojęcia z rejestru" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/concepts/mentions/unlink",
    { name: "Ciemne oświecenie", concept_id: 5, document_id: 11239 }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/odłączone od pojęcia #5/)).toBeTruthy();
});

it("changes a mis-tagged organization into a concept", async () => {
  mockOrgEntities({ id: 31, text: "Ciemne oświecenie", count: 2, organization_id: 8 });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", product_name: "Ciemne oświecenie" } });
  renderInRouter(<EntitiesPanel docId={11239} />);
  await openOrgMenu("Ciemne oświecenie");
  clickRetype("Pojęcie");
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/31/to_product",
    { entity_type: "conceptName" }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/zmienione na pojęcie: Ciemne oświecenie/)).toBeTruthy();
});

it("changes an organization into a named event", async () => {
  mockOrgEntities({ id: 31, text: "Szczyt", count: 2, organization_id: 8 });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", product_name: "Szczyt" } });
  renderInRouter(<EntitiesPanel docId={10872} />);
  await openOrgMenu("Szczyt");
  clickRetype("Wydarzenie");
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/31/to_product",
    { entity_type: "eventName" }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/zmienione na wydarzenie: Szczyt/)).toBeTruthy();
});

it("changes an organization into a person and reports the registry match", async () => {
  mockOrgEntities({ id: 31, text: "Rawit Ruja", count: 2, organization_id: 8 });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", linked: ["Rawit Ruja"] } });
  renderInRouter(<EntitiesPanel docId={10872} />);
  await openOrgMenu("Rawit Ruja");
  clickRetype("Osoba");
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/31/to_person", {},
    { headers: expect.any(Object) }));
  expect(await screen.findByText(/zmienione na osobę: Rawit Ruja/)).toBeTruthy();
});

it("changes a mis-tagged organization into a product / system", async () => {
  mockOrgEntities({ id: 41, text: "Starshield", count: 6, organization_id: 9 });
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", product_name: "Starshield" } });
  renderInRouter(<EntitiesPanel docId={11137} />);
  await openOrgMenu("Starshield");
  clickRetype("Produkt / system");
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/41/to_product", {},
    { headers: expect.any(Object) }));
  expect(await screen.findByText(/zmienione na produkt \/ system: Starshield/)).toBeTruthy();
});

it("offers 'Podświetl w tekście' in the person, organization and place menus when the host asks for it", async () => {
  const person = { id: 11, text: "Hegseth", count: 3 };
  const organization = { id: 12, text: "ONZ", count: 3, organization_id: 5 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [person], orgName: [organization], geogName: [place], placeName: [] } } }));
  const show = vi.fn();
  render(<MemoryRouter><EntitiesPanel docId={10872} onShowInText={show} /></MemoryRouter>);
  for (const [name, kind, item] of [["Hegseth", "persName", person], ["ONZ", "orgName", organization],
    [place.text, "place", place]] as const) {
    await screen.findByRole("button", { name });
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name }));
    fireEvent.click(screen.getByRole("menuitem", { name: "🔎 Podświetl w tekście" }));
    expect(show).toHaveBeenLastCalledWith(expect.objectContaining({ id: item.id, text: item.text }), kind);
  }
});

it("does not add 'Podświetl w tekście' without a host callback", async () => {
  mockOrgEntities({ id: 12, text: "ONZ", count: 3, organization_id: 5 });
  renderInRouter(<EntitiesPanel docId={10753} />);
  await openOrgMenu("ONZ");
  expect(screen.queryByRole("menuitem", { name: /Podświetl/ })).toBeNull();
});

it("preserves reader highlight behavior when menuActions is absent", () => {
  const highlight = vi.fn();
  render(<EntityChips label="Miejsca" items={[place]} highlightMode onHighlight={highlight} />);
  fireEvent.click(screen.getByRole("button"));
  expect(highlight).toHaveBeenCalledWith(place);
  expect(screen.queryByRole("menu")).toBeNull();
});

it("submits rename with Enter without submitting the document form", async () => {
  const submitDocument = vi.fn((event) => event.preventDefault());
  render(<form onSubmit={submitDocument}><MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter></form>);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.keyDown(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" }), { key: "Enter" });
  await waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(1));
  expect(submitDocument).not.toHaveBeenCalled();
});

it("omits merge when there is no other place and keeps edit delete working", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: {
    job: null, entities: { persName: [], orgName: [], geogName: [place], placeName: [] },
  } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  expect(screen.queryByRole("menuitem", { name: "Połącz z innym miejscem" })).toBeNull();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Edytuj" }));
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
  fireEvent.click(screen.getByTitle("Usuń encję (dla osoby usuwa też powiązanie z rejestrem)"));
  expect(screen.getByRole("combobox")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Zakończ edycję" }));
  expect(screen.queryByRole("combobox")).toBeNull();
});

// Copying is available only through existing chip action menus.
const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");
const execCommandDescriptor = Object.getOwnPropertyDescriptor(document, "execCommand");
afterEach(() => {
  if (clipboardDescriptor) Object.defineProperty(navigator, "clipboard", clipboardDescriptor);
  else Reflect.deleteProperty(navigator, "clipboard");
  if (execCommandDescriptor) Object.defineProperty(document, "execCommand", execCommandDescriptor);
  else Reflect.deleteProperty(document, "execCommand");
});
const mockClipboard = (writeText = vi.fn().mockResolvedValue(undefined)) => {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  return writeText;
};

it("copies the exact place name from the first menu entry and closes the menu", async () => {
  const writeText = mockClipboard();
  const { container } = render(<EntityChips label="Miejsca"
    items={[{ text: "Rijadzie", count: 2, entity_type: "placeName" }]}
    menuActions={() => [{ label: "Edytuj", action: vi.fn() }]} />);
  expect(container.querySelector('[aria-label^="Kopiuj nazwę:"]')).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Rijadzie" }));
  expect(screen.getAllByRole("menuitem")[0].textContent).toBe("Kopiuj nazwę");
  await act(async () => {
    fireEvent.click(screen.getByRole("menuitem", { name: "Kopiuj nazwę" }));
  });
  expect(writeText).toHaveBeenCalledExactlyOnceWith("Rijadzie");
  expect(screen.queryByRole("menu")).toBeNull();
  expect(container.querySelector('[aria-label^="Kopiuj nazwę:"]')).toBeNull();
});

it("does not add a menu (or copying) to a chip when menuActions is absent", () => {
  const { container } = renderInRouter(<EntityChips label="Osoby" linkPersons
    items={[{ text: "Paweł Kowalski", count: 1, person_id: 42, entity_type: "persName" }]} />);
  expect(screen.getByRole("link", { name: "Paweł Kowalski ✓" }).getAttribute("href")).toBe("/persons/42");
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.queryByText("Kopiuj nazwę")).toBeNull();
  expect(container.querySelector('[aria-label^="Kopiuj nazwę:"]')).toBeNull();
});

it("offers copying on a person chip whose menu has no other entries", async () => {
  const writeText = mockClipboard();
  render(<EntityChips label="Osoby" menuActions={() => []}
    items={[{ text: "Paweł Kowalski", count: 1, person_id: 42, entity_type: "persName" }]} />);
  fireEvent.click(screen.getByRole("button", { name: "Paweł Kowalski" }));
  expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Kopiuj nazwę", "Szukaj w Google"]);
  await act(async () => {
    fireEvent.click(screen.getByRole("menuitem", { name: "Kopiuj nazwę" }));
  });
  expect(writeText).toHaveBeenCalledExactlyOnceWith("Paweł Kowalski");
});

it.each(["missing", "rejected", "failed fallback"])("handles %s clipboard access safely from the menu", async (mode) => {
  if (mode === "missing") Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
  else mockClipboard(vi.fn().mockRejectedValue(new Error("Clipboard unavailable")));
  const execCommand = vi.fn(() => {
    expect(document.querySelector("textarea")?.value).toBe("Rijadzie");
    if (mode === "failed fallback") throw new Error("Copy unavailable");
    return true;
  });
  Object.defineProperty(document, "execCommand", { configurable: true, value: execCommand });
  render(<EntityChips label="Miejsca" items={[{ text: "Rijadzie", count: 1 }]}
    menuActions={() => [{ label: "Edytuj", action: vi.fn() }]} />);
  const trigger = screen.getByRole("button", { name: "Rijadzie" });
  trigger.focus();
  fireEvent.click(trigger);
  await act(async () => {
    fireEvent.click(screen.getByRole("menuitem", { name: "Kopiuj nazwę" }));
  });
  expect(execCommand).toHaveBeenCalledWith("copy");
  expect(document.querySelector("textarea")).toBeNull();
  expect(document.activeElement).toBe(trigger);
  expect(screen.queryByRole("menu")).toBeNull();
});


it("shows document countries from GET in the editor", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: {
    job: null, entities: {}, countries: [{ slug: "polska", name_pl: "Polska" }],
  } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  expect(await screen.findByText("Polska")).toBeTruthy();
  expect(screen.getByText("Państwa:")).toBeTruthy();
});

it("leaves out the document-wide countries row when hideCountriesRow is set (single-chapter review)", async () => {
  vi.mocked(axios.get).mockResolvedValue({ data: {
    job: null, entities: {}, countries: [{ slug: "salwador", name_pl: "Salwador" }],
  } });
  render(<MemoryRouter><EntitiesPanel docId={11237} hideCountriesRow /></MemoryRouter>);
  await act(async () => {});
  expect(screen.queryByText("Państwa:")).toBeNull();
  expect(screen.queryByText("Salwador")).toBeNull();
});

it.each([
  { countries: [] as { slug: string; name_pl: string }[] },
  { countries: [{ slug: "niemcy", name_pl: "Niemcy" }] },
])("reader countries override GET, including an empty list: $countries", async ({ countries }) => {
  vi.mocked(axios.get).mockResolvedValue({ data: {
    job: null, entities: {}, countries: [{ slug: "polska", name_pl: "Polska" }],
  } });
  render(<EntitiesPanel docId={10753} countries={countries} />);
  await act(async () => {});
  expect(screen.queryByText("Polska")).toBeNull();
  if (countries.length) expect(screen.getByText("Niemcy")).toBeTruthy();
  else expect(screen.queryByText("Państwa:")).toBeNull();
});

it("detects countries, updates chips and reports busy state", async () => {
  let finish!: (value: any) => void;
  vi.mocked(axios.post).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const onBusyChange = vi.fn();
  const onEntitiesChanged = vi.fn();
  render(<EntitiesPanel docId={10753} onBusyChange={onBusyChange} onEntitiesChanged={onEntitiesChanged} />);
  await screen.findByRole("button", { name: place.text });
  onEntitiesChanged.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Wykryj państwa" }));
  expect(axios.post).toHaveBeenCalledWith("/document/10753/countries/detect", {},
    { headers: expect.objectContaining({ "Content-Type": "application/json", "x-api-key": expect.any(String) }) });
  expect((screen.getByRole("button", { name: "Wykrywam państwa..." }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Wykryj osoby, miejsca i obiekty" }) as HTMLButtonElement).disabled).toBe(true);
  expect(onBusyChange).toHaveBeenLastCalledWith(true);
  await act(async () => finish({ data: {
    countries: [{ slug: "polska", name_pl: "Polska" }], added: ["polska"],
  } }));
  expect(screen.getByText("Polska")).toBeTruthy();
  expect(screen.getByText("Dodano państw: 1.")).toBeTruthy();
  expect(onBusyChange).toHaveBeenLastCalledWith(false);
  expect(onEntitiesChanged).toHaveBeenCalledOnce();
  expect((screen.getByRole("button", { name: "Wykryj państwa" }) as HTMLButtonElement).disabled).toBe(false);
});

it.each([false, true])("reports no new countries or a detection error: %s", async (fails) => {
  if (fails) vi.mocked(axios.post).mockRejectedValue({ response: { data: { message: "Database unavailable" } } });
  else vi.mocked(axios.post).mockResolvedValue({ data: { countries: [], added: [] } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await screen.findByRole("button", { name: place.text });
  fireEvent.click(screen.getByRole("button", { name: "Wykryj państwa" }));
  expect(await screen.findByText(fails
    ? "Nie udało się wykryć państw: Database unavailable" : "Nie wykryto nowych państw.")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Wykryj państwa" }) as HTMLButtonElement).disabled).toBe(false);
});

it("explains a network error on entity detection with target, source and a copyable details block", async () => {
  vi.mocked(axios.post).mockRejectedValue({
    message: "Network Error", code: "ERR_NETWORK",
    config: { method: "post", url: "/website_entities", baseURL: "http://192.168.200.7:5055", timeout: 150000 },
  });
  render(<MemoryRouter><EntitiesPanel docId={11226} /></MemoryRouter>);
  await screen.findByRole("button", { name: place.text });
  fireEvent.click(screen.getByRole("button", { name: "Wykryj osoby, miejsca i obiekty" }));
  expect(await screen.findByText(/Nie udało się wykryć encji: brak odpowiedzi serwera/)).toBeTruthy();
  const details = screen.getByText(/^Operacja: Nie udało się wykryć encji/).textContent ?? "";
  expect(details).toContain("Dokument: 11226");
  expect(details).toContain("Żądanie: POST http://192.168.200.7:5055/website_entities");
  expect(details).toContain("Strona (źródło żądania):");
  expect(details).toContain("Czas błędu:");
  expect(details).toContain("Kod błędu klienta: ERR_NETWORK");
  expect(screen.getByRole("button", { name: "Kopiuj szczegóły" })).toBeTruthy();
});

it("proposes geopolitical events with the default model, reports the cost and keeps the panel busy meanwhile", async () => {
  let finish!: (value: any) => void;
  vi.mocked(axios.post).mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const onBusyChange = vi.fn();
  render(<MemoryRouter><EntitiesPanel docId={11205} onBusyChange={onBusyChange} /></MemoryRouter>);
  await screen.findByRole("button", { name: place.text });
  fireEvent.click(screen.getByRole("button", { name: "Zaproponuj relacje geopolityczne" }));
  expect(axios.post).toHaveBeenCalledWith("/document/11205/geopolitics/detect", {},
    { headers: expect.objectContaining({ "x-api-key": expect.any(String) }), timeout: 180000 });
  expect((screen.getByRole("button", { name: "Analizuję geopolitykę..." }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Wykryj państwa" }) as HTMLButtonElement).disabled).toBe(true);
  expect(onBusyChange).toHaveBeenLastCalledWith(true);
  await act(async () => finish({ data: {
    events_created: 6, events_existing: 0, assessments_proposed: 2, assessments_merged: 4, rejected: { bad_date: 1 },
    model: "Bielik-11B-v3.0-Instruct", usage: { llm_cost_amount: "0.0042", llm_cost_currency: "EUR", llm_cost_status: "estimated" },
  } }));
  const message = screen.getByText(/^Geopolityka:/).textContent ?? "";
  expect(message).toContain("6 nowych wydarzeń");
  expect(message).toContain("2 propozycji relacji (+4 dowodów dołączono do istniejących)");
  expect(message).toContain("odrzucone przez walidację: 1");
  expect(message).toContain("Zatwierdź je w Geopolityka → Propozycje");
  expect(message).toContain("Koszt 0.0042 EUR (szacunek), model Bielik-11B-v3.0-Instruct");
  expect(onBusyChange).toHaveBeenLastCalledWith(false);
  expect((screen.getByRole("button", { name: "Zaproponuj relacje geopolityczne" }) as HTMLButtonElement).disabled).toBe(false);
});

it.each(["nothing", "error", "network"])("reports %s of the geopolitics proposal", async (outcome) => {
  if (outcome === "nothing") vi.mocked(axios.post).mockResolvedValue({ data: {
    events_created: 0, events_existing: 0, assessments_proposed: 0, assessments_merged: 0, rejected: {}, model: "m", usage: null,
  } });
  if (outcome === "error") vi.mocked(axios.post).mockRejectedValue({ response: { status: 400, data: { message: "Document has no text content" } } });
  if (outcome === "network") vi.mocked(axios.post).mockRejectedValue({ message: "Network Error" });
  render(<MemoryRouter><EntitiesPanel docId={11205} /></MemoryRouter>);
  await screen.findByRole("button", { name: place.text });
  fireEvent.click(screen.getByRole("button", { name: "Zaproponuj relacje geopolityczne" }));
  const expected = {
    nothing: /model nie znalazł wydarzeń do zapisania.*koszt nieznany/,
    error: /Nie udało się zaproponować relacji geopolitycznych: Document has no text content/,
    network: /Nie udało się zaproponować relacji geopolitycznych: brak odpowiedzi serwera/,
  }[outcome] as RegExp;
  expect(await screen.findByText(expected)).toBeTruthy();
});

it.each(["external", "enrichment"])("disables detection while %s work is active", async (busy) => {
  if (busy === "enrichment") vi.mocked(axios.get).mockResolvedValue({ data: {
    job: { status: "running" }, entities: {},
  } });
  render(<EntitiesPanel docId={10753} externalDisabled={busy === "external"} />);
  await act(async () => {});
  expect((screen.getByRole("button", { name: "Wykryj państwa" }) as HTMLButtonElement).disabled).toBe(true);
});

it.each([false, true])("keeps the place action menu fully opaque (verified: %s)", (verified) => {
  const { container } = render(<EntityChips label="Miejsca"
    items={[{ text: "Arabia", count: 1, entity_type: "placeName", verified }]}
    menuActions={() => [{ label: "Edytuj", action: vi.fn() }]} />);
  const chip = container.querySelector<HTMLElement>('span[style*="position: relative"]');
  expect(chip).not.toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Arabia" }));
  let element: HTMLElement | null = screen.getByRole("menu");
  expect(chip?.contains(element)).toBe(true);
  while (element) {
    expect(["", "1"]).toContain(element.style.opacity);
    if (element === chip) break;
    element = element.parentElement;
  }
  expect(element).toBe(chip);
});

it("offers to split a list of countries and posts the confirmed parts", async () => {
  const compound = { id: 9, text: "Pakistanem Afganistanem", count: 1, split_suggestion: ["Pakistan", "Afganistan"] };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [], orgName: [], geogName: [], placeName: [compound] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", parts: ["Pakistan", "Afganistan"] } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await screen.findByRole("button", { name: compound.text });
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: compound.text }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Podziel na: Pakistan, Afganistan" }));
  expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("Pakistan, Afganistan");
  fireEvent.click(screen.getByRole("button", { name: "Podziel" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/9/split_place",
    { parts: ["Pakistan", "Afganistan"] }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/podzielone na: Pakistan, Afganistan/)).toBeTruthy();
});

it("offers to split glued organization mentions and posts to split_organization", async () => {
  // doc #10872: "W liście do NATO Moskwa wyraźnie wspomina..." became one orgName span.
  const glued = { id: 15887, text: "NATO Moskwa", count: 2, organization_id: 1136 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [], orgName: [glued], geogName: [], placeName: [] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", parts: ["NATO", "Moskwa"] } });
  render(<MemoryRouter><EntitiesPanel docId={10872} /></MemoryRouter>);
  await screen.findByRole("button", { name: glued.text });
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: glued.text }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Podziel na: NATO, Moskwa" }));
  expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("NATO, Moskwa");
  expect(screen.getByText(/osobna organizacja z rejestru/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Podziel" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/15887/split_organization",
    { parts: ["NATO", "Moskwa"] }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/podzielone na: NATO, Moskwa/)).toBeTruthy();
});

it("offers a plain organization split for names without an obvious two-word shape", async () => {
  const long = { id: 31, text: "Rada Bezpieczeństwa ONZ", count: 1, organization_id: 7 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [], orgName: [long], geogName: [], placeName: [] } } }));
  vi.mocked(axios.post).mockRejectedValue({ response: { data: { message: "Podaj od 2 do 6 różnych, niepustych nazw." } } });
  render(<MemoryRouter><EntitiesPanel docId={10872} /></MemoryRouter>);
  await screen.findByRole("button", { name: long.text });
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: long.text }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Podziel na kilka organizacji…" }));
  expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(long.text);
  expect((screen.getByRole("button", { name: "Podziel" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Rada Bezpieczeństwa, ONZ" } });
  fireEvent.click(screen.getByRole("button", { name: "Podziel" }));
  expect(await screen.findByText(/Nie udało się podzielić organizacji: Podaj od 2 do 6/)).toBeTruthy();
});

it("changes a person into a place with an editable name", async () => {
  const person = { id: 11, text: "Kandaharem", count: 1 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [person], orgName: [], geogName: [], placeName: [] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success", place_name: "Kandahar" } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await screen.findByRole("button", { name: person.text });
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: person.text }));
  clickRetype("Miejsce");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Kandahar" } });
  fireEvent.click(screen.getByRole("button", { name: "Zmień na miejsce" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/11/to_place",
    { text: "Kandahar" }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/zmienione na miejsce: Kandahar/)).toBeTruthy();
});

it("excludes a mis-heard person (\"To nie jest osoba\") globally with the reason preselected", async () => {
  const person = { id: 21, text: "Egekwo", count: 1 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [person], orgName: [], geogName: [], placeName: [] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  vi.mocked(axios.delete).mockResolvedValue({ data: { status: "success" } });
  render(<MemoryRouter><EntitiesPanel docId={10872} /></MemoryRouter>);
  await screen.findByRole("button", { name: person.text });
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: person.text }));
  expect(screen.getByRole("menuitem", { name: "× Usuń encję" })).toBeTruthy();
  fireEvent.click(screen.getByRole("menuitem", { name: "🚫 To nie jest osoba" }));
  expect((screen.getByLabelText(/Powód/) as HTMLSelectElement).value).toBe("not_a_person");
  fireEvent.click(screen.getByRole("button", { name: "Globalnie" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/ner_exclusions",
    { entity_text: "Egekwo", entity_type: "persName", scope: "global", document_id: 10872 },
    { headers: expect.any(Object) }));
  await waitFor(() => expect(axios.delete).toHaveBeenCalledWith("/website_entities/21",
    expect.objectContaining({ data: expect.objectContaining({ reason_code: "not_a_person" }) })));
});

it("saves a Wikipedia article for a place and shows the 📖 link", async () => {
  const withWiki = { ...place, wikipedia_url: "https://en.wikipedia.org/wiki/Aden" };
  vi.mocked(axios.put).mockResolvedValue({ data: { status: "success" } });
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  await openMenu();
  expect(screen.getByRole("menuitem", { name: "Otwórz w rejestrze miejsc" }).getAttribute("href"))
    .toBe("/places?name=Jemenu%20P%C3%B3%C5%82nocnego");
  fireEvent.click(screen.getByRole("menuitem", { name: "Dodaj stronę Wikipedii" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: " https://en.wikipedia.org/wiki/Aden " } });
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  await waitFor(() => expect(axios.put).toHaveBeenCalledWith("/places/profile",
    { name: place.text, wikipedia_url: "https://en.wikipedia.org/wiki/Aden" }, { headers: expect.any(Object) }));
  expect(await screen.findByText(/Zapisano artykuł Wikipedii/)).toBeTruthy();
  cleanup();
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [], orgName: [], geogName: [withWiki], placeName: [] } } }));
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  expect((await screen.findByRole("link", { name: `Wikipedia: ${place.text}` })).getAttribute("href"))
    .toBe("https://en.wikipedia.org/wiki/Aden");
});

const relevanceLabel = { related: "Pośrednio", figurative: "Przenośnie" } as const;

it.each(["related", "figurative"] as const)("sets person and place relevance to %s from the chip menu", async (relevance) => {
  const person = { id: 11, text: "Trump", count: 1 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [person], orgName: [], geogName: [place], placeName: [] } } }));
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  for (const item of [person, place]) {
    fireEvent.click(await screen.findByRole("button", { name: item.text }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Związek z tematem: Główny temat/ }));
    expect(screen.getByRole("menuitem", { name: "✓ Główny temat" })).toBeTruthy();
    fireEvent.click(screen.getByRole("menuitem", { name: `○ ${relevanceLabel[relevance]}` }));
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(`/website_entities/${item.id}/relevance`,
      { relevance }, { headers: expect.objectContaining({ "Content-Type": "application/json" }) }));
  }
});

it("reports an error and keeps the previous relevance when saving fails", async () => {
  vi.mocked(axios.patch).mockRejectedValue(new Error("offline"));
  render(<MemoryRouter><EntitiesPanel docId={10753} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: place.text }));
  fireEvent.click(screen.getByRole("menuitem", { name: /Związek z tematem: Główny temat/ }));
  fireEvent.click(screen.getByRole("menuitem", { name: "○ Przenośnie" }));
  expect(await screen.findByText("Nie udało się zapisać związku encji z tematem.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: place.text }));
  expect(screen.getByRole("menuitem", { name: /Związek z tematem: Główny temat/ })).toBeTruthy();
});

it.each(["related", "figurative"] as const)("styles %s chips and explains their relevance", (relevance) => {
  render(<EntityChips label="Miejsca" items={[{ ...place, relevance }]} />);
  const chip = screen.getByText(place.text).closest(".entity-chip");
  expect(chip?.classList.contains(`entity-chip--${relevance}`)).toBe(true);
  expect(chip?.getAttribute("title")).toContain(relevance === "related" ? "Pośredni związek" : "Wzmianka przenośna");
});

it("folds several persons into one target from a single merge dialog", async () => {
  const persons = [
    { id: 1, text: "Luka Nikulesku", count: 7 },
    { id: 2, text: "Nikuleswsku", count: 1 },
    { id: 3, text: "Ninkulesko", count: 1 },
  ];
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: persons, orgName: [], geogName: [], placeName: [] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  render(<MemoryRouter><EntitiesPanel docId={11139} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: /Nikuleswsku/ }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Połącz z inną osobą w dokumencie…" }));
  // Also take the third spelling along, then merge both into the full name.
  const ninkulesko = screen.getByText("Ninkulesko", { selector: "strong" }).parentElement as HTMLElement;
  fireEvent.click(within(ninkulesko).getByRole("checkbox", { name: "dołącz" }));
  const target = screen.getByText("Luka Nikulesku", { selector: "strong" }).parentElement as HTMLElement;
  fireEvent.click(within(target).getByRole("button", { name: "scal 2 do tej osoby" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
  expect(axios.post).toHaveBeenNthCalledWith(1, "/document/11139/persons/merge",
    { source_entity_id: 2, target_entity_id: 1 }, { headers: expect.any(Object) });
  expect(axios.post).toHaveBeenNthCalledWith(2, "/document/11139/persons/merge",
    { source_entity_id: 3, target_entity_id: 1 }, { headers: expect.any(Object) });
  expect(await screen.findByText(/Połączono 2 osoby/)).toBeTruthy();
});
