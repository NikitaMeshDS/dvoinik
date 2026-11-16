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
import { useUnsavedSurvey } from "./useUnsavedSurvey";
import { useHashRoute } from "../../app/useHashRoute";
function Harness({ dirty = true }: { dirty?: boolean }) {
  const { route, navigate } = useHashRoute();
  const leave = useUnsavedSurvey("one", dirty);
  return (
    <>
      <output>{route}</output>
      <a href="#/archive">Архив</a>
      <a href="#/report/one?tab=people">Аудитория</a>
      <button onClick={() => leave(() => navigate("create"))}>Итерация</button>
      <button onClick={() => navigate("admin")}>Доступ</button>
      <button onClick={() => navigate("report/one?tab=people")}>Вкладка</button>
    </>
  );
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});
it("blocks an unsaved preview on leave but allows same-report tab changes", async () => {
  window.history.replaceState(null, "", "#/report/one?tab=validation");
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const view = render(<Harness />);
  fireEvent.click(screen.getByText("Итерация"));
  expect(window.location.hash).toBe("#/report/one?tab=validation");
  const click = new MouseEvent("click", { bubbles: true, cancelable: true });
  screen.getByText("Архив").dispatchEvent(click);
  expect(click.defaultPrevented).toBe(true);
  await act(async () => {
    window.location.hash = "/report/one?tab=people";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(screen.getByRole("status").textContent).toBe("report/one?tab=people");
  const unload = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);
  view.rerender(<Harness dirty={false} />);
  const cleanUnload = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(cleanUnload);
  expect(cleanUnload.defaultPrevented).toBe(false);
});
it("restores a cancelled external hash change before the router loses the preview", async () => {
  window.history.replaceState(null, "", "#/report/one?tab=validation");
  vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<Harness />);
  await act(async () => {
    window.history.replaceState(null, "", "#/archive");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(window.location.hash).toBe("#/report/one?tab=validation");
  expect(screen.getByRole("status").textContent).toBe(
    "report/one?tab=validation",
  );
});
it("allows an explicitly confirmed leave", () => {
  window.history.replaceState(null, "", "#/report/one");
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<Harness />);
  fireEvent.click(screen.getByText("Итерация"));
  expect(window.location.hash).toBe("#/create");
});

it("keeps the Back destination after a cancelled browser Back", async () => {
  window.history.replaceState(null, "", "#/archive");
  window.history.pushState(null, "", "#/report/one?tab=validation");
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<Harness />);
  await act(async () => {
    window.history.back();
  });
  await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
  expect(window.location.hash).toBe("#/report/one?tab=validation");
  confirm.mockReturnValue(true);
  await act(async () => {
    window.history.back();
  });
  await waitFor(() => expect(window.location.hash).toBe("#/archive"));
});

it("guards raw router navigation before it updates React state but permits report tabs", () => {
  window.history.replaceState(null, "", "#/report/one");
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<Harness />);
  fireEvent.click(screen.getByText("Доступ"));
  expect(window.location.hash).toBe("#/report/one");
  expect(screen.getByRole("status").textContent).toBe("report/one");
  confirm.mockClear();
  fireEvent.click(screen.getByText("Вкладка"));
  expect(window.location.hash).toBe("#/report/one?tab=people");
  expect(confirm).not.toHaveBeenCalled();
});
it("cancels the logout event and remains guarded after an allowed logout attempt", () => {
  window.history.replaceState(null, "", "#/report/one");
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<Harness />);
  const logout = vi.fn();
  if (
    window.dispatchEvent(
      new Event("dvoinik:before-leave", { cancelable: true }),
    )
  )
    logout();
  expect(logout).not.toHaveBeenCalled();
  confirm.mockReturnValueOnce(true);
  if (
    window.dispatchEvent(
      new Event("dvoinik:before-leave", { cancelable: true }),
    )
  )
    logout();
  expect(logout).toHaveBeenCalledTimes(1);
  const unload = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);
});
