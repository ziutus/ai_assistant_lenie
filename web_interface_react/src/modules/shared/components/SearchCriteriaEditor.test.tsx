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
});
