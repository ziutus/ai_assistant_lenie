import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import AuthorizationProvider from "./modules/shared/context/authorizationContext";

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
    localStorage.setItem("lenie_apiKey", "test-key");
    const { container } = render(
      <AuthorizationProvider>
        <MemoryRouter initialEntries={["/list"]}>
          <App />
        </MemoryRouter>
      </AuthorizationProvider>,
    );
    expect(container.querySelector(".App")).toBeTruthy();
    localStorage.clear();
  });
});
