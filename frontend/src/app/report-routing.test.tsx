// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Workspace from "./Workspace";
import { api } from "../api";
import sample from "../../../examples/senior-deposit.demo.json";

const session = {
  user: { id: "demo", username: "demo", name: "Demo", role: "demo" as const },
  csrf_token: "test",
  mode: "demo",
  model: "demo",
};
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});
function setup() {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  let reads = 0;
  vi.spyOn(api, "request").mockImplementation(<T,>(path: string) => {
    let value: unknown;
    if (path === "/catalog")
      value = { scenarios: { student_card: sample.scenario }, segments: {} };
    else if (path === "/experiments") value = { records: [sample] };
    else if (path === "/runs" || path === "/recovery") value = { jobs: [] };
    else if (path === "/experiments/" + sample.id) {
      reads++;
      value = sample;
    } else if (path === "/insights") value = null;
    else return Promise.reject(new Error("Unexpected request: " + path));
    return Promise.resolve(value) as Promise<T>;
  });
  return () => reads;
}
it("restores a linked report tab, retains the record and keyboard focus across tab changes and history", async () => {
  const reads = setup();
  window.history.replaceState(
    null,
    "",
    "#/report/" + sample.id + "?tab=validation",
  );
  const view = render(<Workspace session={session} onLogout={() => {}} />);
  const validation = await screen.findByRole("tab", {
    name: "Проверка опросом",
  });
  expect(validation.getAttribute("aria-selected")).toBe("true");
  validation.focus();
  fireEvent.keyDown(validation, { key: "Home" });
  await waitFor(() =>
    expect(window.location.hash).toBe("#/report/" + sample.id),
  );
  const overview = screen.getByRole("tab", { name: "Результат" });
  expect(document.activeElement).toBe(overview);
  expect(reads()).toBe(1);
  await act(async () => {
    window.history.replaceState(
      null,
      "",
      "#/report/" + sample.id + "?tab=validation",
    );
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(validation.getAttribute("aria-selected")).toBe("true");
  expect(reads()).toBe(1);
  view.unmount();
  render(<Workspace session={session} onLogout={() => {}} />);
  expect(
    (await screen.findByRole("tab", { name: "Проверка опросом" })).getAttribute(
      "aria-selected",
    ),
  ).toBe("true");
});
it("falls back to the overview for unknown linked tabs without corrupting the record id", async () => {
  setup();
  window.history.replaceState(
    null,
    "",
    "#/report/" + sample.id + "?tab=unknown",
  );
  render(<Workspace session={session} onLogout={() => {}} />);
  expect(
    (await screen.findByRole("tab", { name: "Результат" })).getAttribute(
      "aria-selected",
    ),
  ).toBe("true");
});

it("does not log out when the report's pending-work guard cancels the action", async () => {
  setup();
  window.history.replaceState(null, "", "#/archive");
  const logout = vi.fn();
  render(
    <Workspace
      session={{ ...session, user: { ...session.user, role: "analyst" } }}
      onLogout={logout}
    />,
  );
  const menu = await screen.findByLabelText("Меню пользователя");
  fireEvent.click(menu);
  const cancel = (event: Event) => event.preventDefault();
  window.addEventListener("dvoinik:before-leave", cancel);
  try {
    fireEvent.click(screen.getByRole("button", { name: /^Выйти$/ }));
    expect(logout).not.toHaveBeenCalled();
  } finally {
    window.removeEventListener("dvoinik:before-leave", cancel);
  }
});
