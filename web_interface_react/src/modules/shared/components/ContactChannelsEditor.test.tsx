import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import ContactChannelsEditor, { type ContactChannel } from "./ContactChannelsEditor";

afterEach(cleanup);

function Harness() {
  const [entries, setEntries] = React.useState<ContactChannel[]>([{ value: "111", label: "dom" }]);
  return <ContactChannelsEditor title="Telefony" kind="tel" entries={entries} onChange={setEntries} />;
}

it("adds a labeled number, promotes it and removes the old primary without losing the other entry", () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole("button", { name: "Dodaj telefon" }));
  fireEvent.change(screen.getByLabelText("Telefony: wartość 2"), { target: { value: "222" } });
  fireEvent.change(screen.getByLabelText("Telefony: etykieta 2"), { target: { value: "praca" } });
  fireEvent.click(screen.getByRole("button", { name: "Ustaw jako główny" }));
  expect(screen.getByLabelText("Telefony: wartość 1")).toHaveProperty("value", "222");
  expect(screen.getByLabelText("Telefony: etykieta 1")).toHaveProperty("value", "praca");
  expect(screen.getByLabelText("Telefony: wartość 2")).toHaveProperty("value", "111");
  fireEvent.click(screen.getByRole("button", { name: "Telefony: usuń 2" }));
  expect(screen.queryByLabelText("Telefony: wartość 2")).toBeNull();
  expect(screen.getByLabelText("Telefony: wartość 1")).toHaveProperty("value", "222");
  fireEvent.click(screen.getByRole("button", { name: "Telefony: usuń 1" }));
  expect(screen.queryByLabelText("Telefony: wartość 1")).toBeNull();
});
