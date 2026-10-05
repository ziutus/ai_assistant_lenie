import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MultiSelectFilter from "./MultiSelectFilter";

afterEach(cleanup);

const options = [{ value: "1", label: "Praca" }, { value: "2", label: "Nauka" }];
const emptyOption = { value: "empty", label: "(bez tematów)" };

function setup(withEmpty = true) {
  const onChange = vi.fn();
  const onTelemetry = vi.fn();
  function Filter() {
    const [values, setValues] = React.useState(["1"]);
    return <MultiSelectFilter options={options} selectedValues={values}
      emptyOption={withEmpty ? emptyOption : undefined}
      labels={{ all: "Wszystkie tematy", selected: "Tematy", heading: "Wybierz tematy:" }}
      onChange={next => { onChange(next); setValues(next); }} onTelemetry={onTelemetry} />;
  }
  const view = render(<Filter />);
  const details = view.container.querySelector("details")!;
  fireEvent.click(screen.getByText("Tematy: wybrano 1"));
  return { ...view, details, onChange, onTelemetry };
}

describe("MultiSelectFilter", () => {
  it("selects all, deselects and inverts, including the empty option", () => {
    const { onChange, onTelemetry } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Zaznacz wszystkie" }));
    expect(onChange).toHaveBeenLastCalledWith(["1", "2", "empty"]);
    expect(screen.getByText("Wszystkie tematy")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Odznacz wszystkie" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
    expect(screen.getByText("Tematy: wybrano 0")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Nauka"));
    fireEvent.click(screen.getByRole("button", { name: "Odwróć wybór" }));
    expect(onChange).toHaveBeenLastCalledWith(["1", "empty"]);
    expect(onTelemetry).toHaveBeenCalledTimes(4);
  });

  it("selects only a regular or empty option and reports every change", () => {
    const { onChange, onTelemetry } = setup();
    fireEvent.click(screen.getByRole("button", { name: "Tylko Nauka" }));
    expect(onChange).toHaveBeenLastCalledWith(["2"]);
    fireEvent.click(screen.getByRole("button", { name: "Tylko (bez tematów)" }));
    expect(onChange).toHaveBeenLastCalledWith(["empty"]);
    fireEvent.click(screen.getByLabelText("(bez tematów)"));
    expect(onChange).toHaveBeenLastCalledWith([]);
    fireEvent.click(screen.getByLabelText("(bez tematów)"));
    expect(onChange).toHaveBeenLastCalledWith(["empty"]);
    expect(onTelemetry).toHaveBeenCalledTimes(4);
  });

  it("supports filters without an empty option", () => {
    const { onChange } = setup(false);
    expect(screen.queryByLabelText("(bez tematów)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Zaznacz wszystkie" }));
    expect(onChange).toHaveBeenLastCalledWith(["1", "2"]);
  });

  it("keeps internal actions open, closes outside and removes its listener on unmount", () => {
    const { details, unmount } = setup();
    expect(details.open).toBe(true);
    const only = screen.getByRole("button", { name: "Tylko Nauka" });
    fireEvent.pointerDown(only);
    fireEvent.click(only);
    expect(details.open).toBe(true);
    fireEvent.pointerDown(screen.getByLabelText("Praca"));
    expect(details.open).toBe(true);
    fireEvent.pointerDown(document.body);
    expect(details.open).toBe(false);
    const remove = vi.spyOn(document, "removeEventListener");
    unmount();
    expect(remove).toHaveBeenCalledWith("pointerdown", expect.any(Function));
    remove.mockRestore();
  });
});
