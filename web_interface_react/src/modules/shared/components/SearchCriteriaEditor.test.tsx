import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SearchCriteriaEditor } from "./SearchCriteriaEditor";
import { criteriaFixture } from "../utils/searchCriteria.fixture";

describe("SearchCriteriaEditor", () => {
  it("edits topic and filter chips", () => {
    const onChange = vi.fn();
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={onChange} onApply={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Temat"), { target: { value: "energia" } });
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].query).toBe("energia");
    fireEvent.change(screen.getByLabelText("Okres od"), { target: { value: "2010" } });
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].subject_period_start_year).toBe(2010);
  });

  it("removes a filter and applies corrected criteria", () => {
    const onChange = vi.fn();
    const onApply = vi.fn();
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={onChange} onApply={onApply} />);
    fireEvent.click(screen.getByLabelText("Usuń filtr Wydawca"));
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].publisher_name).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Szukaj z poprawionymi kryteriami" }));
    expect(onApply).toHaveBeenCalledOnce();
  });

  it("shows every possible filter, including ones Bielik never set, and lets the user fill them in", () => {
    const onChange = vi.fn();
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={onChange} onApply={vi.fn()} />);
    // author_name is null in the fixture — there is no "Usuń filtr Autor" button for it yet...
    expect(screen.queryByLabelText("Usuń filtr Autor")).toBeNull();
    // ...but the field itself is still visible and editable.
    fireEvent.change(screen.getByLabelText("Autor"), { target: { value: "Jan Kowalski" } });
    expect(onChange.mock.calls[onChange.mock.calls.length - 1]?.[0].author_name).toBe("Jan Kowalski");
  });

  it("supports a custom title and apply-button label for the advanced-search entry point", () => {
    render(<SearchCriteriaEditor criteria={criteriaFixture()} disabled={false}
      onChange={vi.fn()} onApply={vi.fn()} title="Kryteria wyszukiwania" applyLabel="Szukaj" />);
    expect(screen.getByRole("heading", { name: "Kryteria wyszukiwania" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Szukaj" })).toBeTruthy();
  });
});
