// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import WorkspaceShell from "./WorkspaceShell";
import type { Session } from "../types";
const session: Session = {
  user: { id: "demo", username: "demo", name: "Demo", role: "demo" },
  csrf_token: "test",
  mode: "demo",
  model: "demo",
};
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it("route changes focus the new workspace while same-page updates preserve control focus", () => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const page = (route: string) => (
    <WorkspaceShell
      session={session}
      route={route}
      navigate={() => {}}
      onLogout={() => {}}
      toast=""
      onDismiss={() => {}}
    >
      <h1>{route}</h1>
      <button>Настроить</button>
    </WorkspaceShell>
  );
  const { rerender } = render(page("report/test"));
  screen.getByRole("button", { name: "Настроить" }).focus();
  rerender(page("create"));
  expect(document.activeElement).toBe(screen.getByRole("main"));
  const settings = screen.getByRole("button", { name: "Настроить" });
  settings.focus();
  rerender(page("create"));
  expect(document.activeElement).toBe(settings);
});
