import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ArticleSourceComparison from "./articleSourceComparison";

const lead = "Analiza narracji, aktywności publikacyjnej i mechanizmów oddziaływania modelu.";
const first = "Doniesienia o atakach na infrastrukturę serwerową Yandexu oraz spadek ruchu.";
const last = "Wnioski końcowe dotyczą ograniczonego wpływu zakłóceń infrastruktury.";
const footer = "Stopka portalu z informacją o prawach autorskich i polityce prywatności.";
const html = `<p>${lead}</p><p>${first}</p><p>${last}</p><p>${footer}</p>`;

const setup = () => {
  const setFieldValue = vi.fn();
  const formik = { setFieldValue, values: { text_raw: html, text_md: `${first}\n\n${last}`, url: "" } };
  render(<ArticleSourceComparison formik={formik} />);
  return setFieldValue;
};

describe("ArticleSourceComparison", () => {
  it("prepends an omitted source paragraph to text_md", () => {
    const setFieldValue = setup();
    fireEvent.click(screen.getAllByText("＋")[0]);
    expect(setFieldValue).toHaveBeenCalledWith("text_md", `${lead}\n\n${first}\n\n${last}`);
  });

  it("appends an omitted trailing paragraph to text_md", () => {
    const setFieldValue = setup();
    const buttons = screen.getAllByText("＋");
    fireEvent.click(buttons[buttons.length - 1]);
    expect(setFieldValue).toHaveBeenCalledWith("text_md", `${first}\n\n${last}\n\n${footer}`);
  });
});
