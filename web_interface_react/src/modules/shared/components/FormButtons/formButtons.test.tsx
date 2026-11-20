import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import FormButtons from "./formButtons";

afterEach(cleanup);

const mount = (values: Record<string, unknown>, isLoading = false) => {
  const next = vi.fn();
  const save = vi.fn();
  render(<FormButtons message="" isError={false} isLoading={isLoading} formik={{ values }}
    handleSaveWebsiteNext={next} handleSaveWebsiteToCorrect={save} />);
  return { next, save };
};
const youtube = { document_type: "youtube", text: "## Wstęp\n\nTekst." };

it("offers the NER review and a direct chunk shortcut for a YouTube transcript", () => {
  const { next } = mount(youtube);
  fireEvent.click(screen.getByRole("button", { name: "Zapisz i przejdź do przeglądu NER" }));
  expect(next).toHaveBeenLastCalledWith(youtube, "ner");
  fireEvent.click(screen.getByRole("button", { name: "Przejdź prosto do chunków" }));
  expect(next).toHaveBeenLastCalledWith(youtube, "chunks");
  expect(screen.queryByText("Zapisz tekst i przejdź do analizy chunków")).toBeNull();
});

it("disables both continue buttons without a transcript or while saving", () => {
  mount({ document_type: "youtube", text: "  " });
  expect((screen.getByRole("button", { name: "Zapisz i przejdź do przeglądu NER" }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Przejdź prosto do chunków" }) as HTMLButtonElement).disabled).toBe(true);
  cleanup();
  mount(youtube, true);
  expect((screen.getByRole("button", { name: "Przejdź prosto do chunków" }) as HTMLButtonElement).disabled).toBe(true);
});

it("keeps the other document types unchanged", () => {
  mount({ document_type: "webpage", text: "x" });
  expect(screen.getByRole("button", { name: "Zatwierdź Markdown i przejdź do chunków" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Przejdź prosto do chunków" })).toBeNull();
  cleanup();
  mount({ document_type: "movie", text: "x" });
  expect(screen.getByRole("button", { name: "Zapisz jako gotowy i przejdź dalej" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Przejdź prosto do chunków" })).toBeNull();
});

it("still has the plain save button", () => {
  const { save } = mount(youtube);
  fireEvent.click(screen.getByRole("button", { name: "Zapisz" }));
  expect(save).toHaveBeenCalledWith(youtube);
});

it("shows the technical details under an error message, and hides them for a success message", () => {
  const props = { isLoading: false, formik: { values: { document_type: "webpage", text: "x" } },
    handleSaveWebsiteNext: vi.fn(), handleSaveWebsiteToCorrect: vi.fn() };
  render(<FormButtons {...props} message="Nie udało się zapisać dokumentu: brak odpowiedzi serwera"
    isError errorDetails={"Operacja: zapis\nOdpowiedź HTTP: brak"} />);
  expect(screen.getByText("Szczegóły techniczne")).toBeTruthy();
  expect(screen.getByText(/Odpowiedź HTTP: brak/)).toBeTruthy();
  cleanup();
  render(<FormButtons {...props} message="Zapisano" isError={false} errorDetails="stare szczegóły" />);
  expect(screen.queryByText("Szczegóły techniczne")).toBeNull();
});
