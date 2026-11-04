import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import MarkdownLineEditor from "./markdownLineEditor";

afterEach(cleanup);
const makeFormik = () => ({ values: { text_md: "Linia 1\nLinia 2" }, setFieldValue: vi.fn() });

it("saves the current values with the Zapisz button under the article text", () => {
  const formik = makeFormik();
  const onSave = vi.fn();
  render(<MarkdownLineEditor formik={formik} disabled={false} onSave={onSave} />);
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  expect(onSave).toHaveBeenCalledWith(formik.values);
});

it("applies the edited Markdown and saves it in one step", () => {
  const formik = makeFormik();
  const onSave = vi.fn();
  render(<MarkdownLineEditor formik={formik} disabled={false} onSave={onSave} />);
  fireEvent.click(screen.getByRole("button", { name: "Edytuj cały Markdown" }));
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Nowy tekst" } });
  fireEvent.click(screen.getByRole("button", { name: "Zastosuj i zapisz" }));
  expect(formik.setFieldValue).toHaveBeenCalledWith("text_md", "Nowy tekst");
  expect(onSave).toHaveBeenCalledWith({ text_md: "Nowy tekst" });
});

it("shows no save button without onSave", () => {
  render(<MarkdownLineEditor formik={makeFormik()} disabled={false} />);
  expect(screen.queryByRole("button", { name: "Zapisz" })).toBeNull();
});
