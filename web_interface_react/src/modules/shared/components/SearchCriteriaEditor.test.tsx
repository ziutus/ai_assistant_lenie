import axios from "axios";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SearchCriteriaEditor } from "./SearchCriteriaEditor";
import { criteriaFixture } from "../utils/searchCriteria.fixture";

vi.mock("axios");
const mockedGet = axios.get as unknown as ReturnType<typeof vi.fn>;

describe("SearchCriteriaEditor", () => {
  beforeEach(() => {
    // Default: GET /languages returns nothing, so the languages field stays the free-text
    // fallback in tests that don't care about the picker — matches an empty/unreachable backend.
    mockedGet.mockReset().mockResolvedValue({ data: { languages: [] } });
  });

  it("edits topic and filter chips", async () => {
    const onChange = vi.fn();
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={onChange} onApply={vi.fn()} />);
    await screen.findByLabelText("Temat"); // let the GET /languages effect settle first
    fireEvent.change(screen.getByLabelText("Temat"), { target: { value: "energia" } });
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].query).toBe("energia");
    fireEvent.change(screen.getByLabelText("Okres od"), { target: { value: "2010" } });
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].subject_period_start_year).toBe(2010);
  });

  it("removes a filter and applies corrected criteria", async () => {
    const onChange = vi.fn();
    const onApply = vi.fn();
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={onChange} onApply={onApply} />);
    await screen.findByLabelText("Temat");
    fireEvent.click(screen.getByLabelText("Usuń filtr Wydawca"));
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].publisher_name).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Szukaj z poprawionymi kryteriami" }));
    expect(onApply).toHaveBeenCalledOnce();
  });

  it("shows every possible filter, including ones Bielik never set, and lets the user fill them in", async () => {
    const onChange = vi.fn();
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={onChange} onApply={vi.fn()} />);
    await screen.findByLabelText("Temat");
    // author_name is null in the fixture — there is no "Usuń filtr Autor" button for it yet...
    expect(screen.queryByLabelText("Usuń filtr Autor")).toBeNull();
    // ...but the field itself is still visible and editable.
    fireEvent.change(screen.getByLabelText("Autor"), { target: { value: "Jan Kowalski" } });
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].author_name).toBe("Jan Kowalski");
  });

  it("renders document_types as checkboxes and toggles them without free text", async () => {
    const onChange = vi.fn();
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={onChange} onApply={vi.fn()} />);
    await screen.findByLabelText("Temat");
    // criteriaFixture() already has document_types: ["webpage"]
    expect(screen.getByRole("checkbox", { name: "Strona WWW" })).toHaveProperty("checked", true);
    expect(screen.getByRole("checkbox", { name: "YouTube" })).toHaveProperty("checked", false);
    fireEvent.click(screen.getByRole("checkbox", { name: "YouTube" }));
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].document_types)
      .toEqual(["webpage", "youtube"]);
    fireEvent.click(screen.getByRole("checkbox", { name: "Strona WWW" }));
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].document_types).toEqual([]);
  });

  it("renders languages as checkboxes once GET /languages resolves, replacing the free-text field", async () => {
    mockedGet.mockResolvedValue({ data: { languages: [
      { code: "pl", name_pl: "polski", count: 8182 },
      { code: "en", name_pl: "angielski", count: 164 },
    ] } });
    const onChange = vi.fn();
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={onChange} onApply={vi.fn()} />);
    // criteriaFixture() already has languages: ["pl"]
    expect(await screen.findByRole("checkbox", { name: "polski (pl) · 8182" })).toHaveProperty("checked", true);
    expect(screen.queryByLabelText("Języki")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "angielski (en) · 164" }));
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].languages).toEqual(["pl", "en"]);
  });

  it("keeps languages as a free-text field when GET /languages has nothing to offer", async () => {
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={vi.fn()} onApply={vi.fn()} />);
    await screen.findByLabelText("Temat");
    expect(screen.getByLabelText("Języki")).toHaveProperty("value", "pl");
  });

  it("shows Publikacja/Dodano filters as date pickers", async () => {
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={vi.fn()} onApply={vi.fn()} />);
    await screen.findByLabelText("Temat");
    expect(screen.getByLabelText("Publikacja od")).toHaveProperty("type", "date");
    expect(screen.getByLabelText("Dodano od")).toHaveProperty("type", "date");
  });

  it("supports a custom title and apply-button label for the advanced-search entry point", async () => {
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={vi.fn()} onApply={vi.fn()} title="Kryteria wyszukiwania" applyLabel="Szukaj" />);
    await screen.findByLabelText("Temat");
    expect(screen.getByRole("heading", { name: "Kryteria wyszukiwania" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Szukaj" })).toBeTruthy();
  });
});
