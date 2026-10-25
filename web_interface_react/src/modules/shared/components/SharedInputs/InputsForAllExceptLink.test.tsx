import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import InputsForAllExceptLink from "./InputsForAllExceptLink";

vi.mock("../EntitiesPanel/entitiesPanel", () => ({ default: () => null }));
vi.mock("../ArticlePreparationPanel/articlePreparationPanel", () => ({ default: () => null }));
vi.mock("../MarkdownLineEditor/markdownLineEditor", () => ({ default: () => null }));
vi.mock("../ArticleSourceComparison/articleSourceComparison", () => ({ default: () => null }));
afterEach(cleanup);
const formik = { values: { document_type: "youtube", text: "## Rozdział\n\nTekst.", text_md: "Markdown",
  chapter_list: "0:00 Rozdział", outline_md: "Plan", note: "Notatka" }, handleChange: vi.fn() };

it.each([undefined, false, true])("hides only the text input when hideText=%s without altering form values", hideText => {
  render(<InputsForAllExceptLink formik={formik} isLoading={false} handleRemoveNotNeededText={vi.fn()} hideText={hideText} />);
  expect(screen.queryByLabelText("Website content") !== null).toBe(!hideText);
  expect(screen.getByLabelText("Note:")).toBeTruthy();
  expect(screen.getByLabelText("Chapter list:")).toBeTruthy();
  expect(screen.getByLabelText("Spis treści (AI) — Markdown:")).toBeTruthy();
  expect(screen.getByText("Website MarkDown content")).toBeTruthy();
  expect(formik.values.text).toBe("## Rozdział\n\nTekst.");
  expect(formik.handleChange).not.toHaveBeenCalled();
});
