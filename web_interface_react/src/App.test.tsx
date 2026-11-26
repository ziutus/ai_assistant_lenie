import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import AuthorizationProvider from "./modules/shared/context/authorizationContext";

vi.mock("axios", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { app_version: "test" } }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}));
vi.mock("./modules/shared/components/Authorization/authorization", () => ({
  default: () => null,
}));
vi.mock("./modules/shared/pages/list", () => ({
  default: () => <div data-testid="list-page" />,
}));

describe("App", () => {
  it("renders connect page when no API key is set", () => {
    localStorage.clear();
    const { container } = render(
      <AuthorizationProvider>
        <MemoryRouter initialEntries={["/list"]}>
          <App />
        </MemoryRouter>
      </AuthorizationProvider>,
    );
    // Should redirect to /connect since no API key
    expect(container.querySelector("h2")?.textContent).toBe("Connect to Lenie Backend");
  });

  it("renders app layout when API key is set", () => {
    localStorage.setItem("lenie_apiKey", btoa("test-key"));
    const { container } = render(
      <AuthorizationProvider>
        <MemoryRouter initialEntries={["/list"]}>
          <App />
        </MemoryRouter>
      </AuthorizationProvider>,
    );
    expect(container.querySelector(".App")).toBeTruthy();
    const registryLink = container.querySelector('a[href="/company-registry"]');
    expect(registryLink?.textContent).toBe("Rejestr firm");
    expect(registryLink?.previousElementSibling?.getAttribute("href")).toBe("/organizations");
    localStorage.clear();
  });

  it("opens the company registry inside the authenticated layout", () => {
    localStorage.setItem("lenie_apiKey", btoa("test-key"));
    const { container } = render(
      <AuthorizationProvider><MemoryRouter initialEntries={["/company-registry"]}>
        <App />
      </MemoryRouter></AuthorizationProvider>,
    );
    expect(container.querySelector('[aria-label="Rejestr firm"] h1')?.textContent).toBe("Rejestr firm");
    localStorage.clear();
  });

  it("requires authentication for the company registry", () => {
    localStorage.clear();
    const { container } = render(
      <AuthorizationProvider><MemoryRouter initialEntries={["/company-registry"]}>
        <App />
      </MemoryRouter></AuthorizationProvider>,
    );
    expect(container.querySelector("h2")?.textContent).toBe("Connect to Lenie Backend");
  });
});
