// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ImportDialog } from "./Compare";
import { api } from "./api";
import sample from "../../examples/senior-deposit.demo.json";

beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value() {
      this.removeAttribute("open");
    },
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
function deferred() {
  let resolve!: (value: string) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<string>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function file(name: string, text: () => Promise<string>) {
  const result = new File(["test"], name, { type: "application/json" });
  Object.defineProperty(result, "text", { value: text });
  return result;
}
function dialog() {
  const imported = vi.fn(),
    closed = vi.fn();
  const request = vi.spyOn(api, "request").mockResolvedValue(sample);
  const view = render(<ImportDialog onClose={closed} onImported={imported} />);
  return {
    ...view,
    imported,
    closed,
    request,
    input: screen.getByLabelText("JSON исследования") as HTMLInputElement,
  };
}
it("disables import while reading and imports the latest selected file even when the first finishes last", async () => {
  const first = deferred(),
    second = deferred();
  const { input, request } = dialog();
  fireEvent.change(input, {
    target: { files: [file("first.json", () => first.promise)] },
  });
  expect(screen.getByText("Читаем JSON…")).toBeTruthy();
  expect(
    (screen.getByRole("button", { name: "Импортировать" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.change(input, {
    target: { files: [file("second.json", () => second.promise)] },
  });
  await act(async () => second.resolve("second contents"));
  await act(async () => first.resolve("first contents"));
  expect(screen.getByText("second.json")).toBeTruthy();
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Импортировать" })),
  );
  expect(request).toHaveBeenCalledWith("/import", "POST", {
    content: "second contents",
  });
});
it("resets the picker for a same-file retry and shows an actionable read failure", async () => {
  const read = deferred();
  const { input, request } = dialog();
  Object.defineProperty(input, "value", {
    configurable: true,
    writable: true,
    value: "C:\\fakepath\\unreadable.json",
  });
  fireEvent.change(input, {
    target: { files: [file("unreadable.json", () => read.promise)] },
  });
  expect(input.value).toBe("");
  await act(async () => read.reject(new Error("read failed")));
  expect(screen.getByRole("alert").textContent).toContain(
    "Выберите файл ещё раз",
  );
  expect(input.disabled).toBe(false);
  expect(request).not.toHaveBeenCalled();
  await act(async () =>
    fireEvent.change(input, {
      target: {
        files: [file("unreadable.json", () => Promise.resolve("recovered"))],
      },
    }),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Импортировать" })),
  );
  expect(request).toHaveBeenCalledWith("/import", "POST", {
    content: "recovered",
  });
});
it("keeps the latest file ready when an older read fails", async () => {
  const first = deferred();
  const { input } = dialog();
  fireEvent.change(input, {
    target: { files: [file("first.json", () => first.promise)] },
  });
  await act(async () =>
    fireEvent.change(input, {
      target: { files: [file("second.json", () => Promise.resolve("second"))] },
    }),
  );
  await act(async () => first.reject(new Error("stale failure")));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(
    (screen.getByRole("button", { name: "Импортировать" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
});
it("an oversized replacement invalidates a pending read and cannot import its old contents", async () => {
  const first = deferred();
  const { input, request } = dialog();
  fireEvent.change(input, {
    target: { files: [file("first.json", () => first.promise)] },
  });
  const tooLarge = file("large.json", () => Promise.resolve("unused"));
  Object.defineProperty(tooLarge, "size", { value: 5 * 1024 * 1024 + 1 });
  fireEvent.change(input, { target: { files: [tooLarge] } });
  await act(async () => first.resolve("first"));
  expect(screen.getByText("large.json")).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain("5 МБ");
  expect(
    (screen.getByRole("button", { name: "Импортировать" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  expect(request).not.toHaveBeenCalled();
});
it("settles a pending read rejection after the dialog unmounts", async () => {
  const read = deferred();
  const { input, unmount, imported, request } = dialog();
  fireEvent.change(input, {
    target: { files: [file("pending.json", () => read.promise)] },
  });
  unmount();
  await act(async () => read.reject(new Error("read failed after close")));
  expect(imported).not.toHaveBeenCalled();
  expect(request).not.toHaveBeenCalled();
});
