import axios from "axios";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
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

it("shows the full proposal and confirms it without edit mode", async () => {
  const proposed = { id: 7, text: "Huty", count: 4, verified: false, place_verification_status: "needs_review",
    proposed_geocode_id: 17, proposed_display_name: "Huti, obwód lwowski, Ukraina", proposed_lat: 49, proposed_lon: 24 };
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null } : { entities: { persName: [], orgName: [], geogName: [proposed], placeName: [] } } }));
  vi.mocked(axios.post).mockResolvedValue({ data: { status: "success" } });
  render(<EntitiesPanel docId={10753} />);
  expect(await screen.findByText(/Wymaga potwierdzenia/)).toBeTruthy();
  expect(screen.getByText("Propozycja lokalizacji: Huti, obwód lwowski, Ukraina")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź tę lokalizację" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith("/website_entities/7/confirm_place",
    { selected_geocode_id: 17 }, { headers: expect.any(Object) }));
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(3));
});

it("renames a place without edit mode and refetches entities", async () => {
  render(<EntitiesPanel docId={10753} />);
  await openMenu();
  expect(screen.getAllByRole("menuitem")).toHaveLength(4);
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

it.each([false, true])("offers merge after rename (conflict: %s)", async (conflict) => {
  const target = { id: 8, text: "Aden", entity_type: "placeName" };
  if (conflict) {
    vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: { conflict_entity: target } } });
  } else {
    vi.mocked(axios.patch).mockResolvedValue({ data: { geocoded: true, same_place_entity: target } });
  }
  vi.mocked(axios.post).mockResolvedValue({ data: {} });
  render(<EntitiesPanel docId={10753} />);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" }), { target: { value: "Aden" } });
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

it("shows a backend conflict and keeps the form open", async () => {
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 409, data: { message: "Wybierz „Połącz z innym miejscem”." } } });
  render(<EntitiesPanel docId={10753} />);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
  expect(await screen.findByText("Wybierz „Połącz z innym miejscem”.")).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeTruthy();
});

it("reloads the list and closes the form when the renamed entity no longer exists", async () => {
  vi.mocked(axios.patch).mockRejectedValue({ response: { status: 404, data: { message: "Nie znaleziono encji." } } });
  render(<EntitiesPanel docId={10753} />);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  fireEvent.click(screen.getByRole("button", { name: "Zatwierdź" }));
  expect(await screen.findByText(/Ta encja już nie istnieje/)).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
  expect(axios.get).toHaveBeenCalledTimes(3);
});

it.each(["× Usuń encję", "🚫 Usuń i nie wykrywaj więcej", "Połącz z innym miejscem"])(
  "opens the existing %s flow without edit mode", async (action) => {
    render(<EntitiesPanel docId={10753} />);
    await openMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: action }));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("button", { name: "Edytuj" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "✕ anuluj" })).toBeTruthy();
    if (action !== "Połącz z innym miejscem") expect(screen.getByRole("combobox")).toBeTruthy();
  },
);

it("closes on outside pointerdown and Escape, and clears rename on document change", async () => {
  const view = render(<EntitiesPanel docId={10753} />);
  await openMenu();
  fireEvent.pointerDown(document.body);
  expect(screen.queryByRole("menu")).toBeNull();
  await openMenu();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("menu")).toBeNull();
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  view.rerender(<EntitiesPanel docId={10754} />);
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
});

it("refetches and clears open forms when refreshKey changes for the same document", async () => {
  const view = render(<EntitiesPanel docId={10753} refreshKey={0} />);
  await openMenu();
  fireEvent.click(screen.getByRole("menuitem", { name: "Popraw nazwę" }));
  expect(screen.getByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeTruthy();
  const callsBefore = vi.mocked(axios.get).mock.calls.length;
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [], placeName: [] } } }));
  view.rerender(<EntitiesPanel docId={10753} refreshKey={1} />);
  await waitFor(() => expect(vi.mocked(axios.get).mock.calls.length).toBe(callsBefore + 2));
  expect(screen.queryByRole("textbox", { name: "Popraw nazwę miejsca" })).toBeNull();
  expect(screen.queryByRole("button", { name: place.text })).toBeNull();
});

const emptyEntities = { persName: [], orgName: [], geogName: [], placeName: [] };

it("does not announce completion for a stale finished job it never saw running", async () => {
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: { id: "old", status: "done", progress: null } }
    : { entities: emptyEntities } }));
  render(<EntitiesPanel docId={10753} />);
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
  render(<EntitiesPanel docId={10753} />);
  expect(await screen.findByText("Pełna weryfikacja encji zakończona.", {}, { timeout: 6000 })).toBeTruthy();
}, 10000);

it("shows read-only place tags under Miejsca only when the document has them", async () => {
  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [place], placeName: [] },
      place_tags: ["miejsce-aden", "miejsce-rijad"] } }));
  const view = render(<EntitiesPanel docId={10753} />);
  expect(await screen.findByText("Tagi miejsc: miejsce-aden, miejsce-rijad")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Czym są tagi miejsc" }));
  expect(screen.getByRole("note").textContent).toContain("nie ma osobnego filtra po tagach");
  view.unmount();

  vi.mocked(axios.get).mockImplementation(async (url) => ({ data: url.endsWith("enrichment_job")
    ? { job: null }
    : { entities: { persName: [], orgName: [], geogName: [place], placeName: [] } } }));
  render(<EntitiesPanel docId={10753} />);
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
    "Otwórz w rejestrze źródeł", "Popraw nazwę", "Dane źródła (typ, strona, opis)",
    "Połącz z inną organizacją", "× Usuń encję", "🚫 Usuń i nie wykrywaj więcej",
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
    "Otwórz w rejestrze organizacji", "Popraw nazwę", "Opis organizacji",
    "Połącz z inną organizacją", "× Usuń encję", "🚫 Usuń i nie wykrywaj więcej",
  ]);
  fireEvent.click(screen.getByRole("menuitem", { name: "Opis organizacji" }));
  expect(screen.getByText(/Krótki opis dla:/)).toBeTruthy();
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
  render(<form onSubmit={submitDocument}><EntitiesPanel docId={10753} /></form>);
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
  render(<EntitiesPanel docId={10753} />);
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
