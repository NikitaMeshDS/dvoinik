// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ValidationPanel from "./features/reports/ValidationPanel";
import sample from "../../examples/senior-deposit.demo.json";
import type { Experiment } from "./types";
const record = sample as unknown as Experiment;
function panel() {
  render(
    <ValidationPanel
      record={record}
      catalog={{ scenarios: {}, segments: {} }}
      onUpdated={() => {}}
      onExport={() => {}}
    />,
  );
  return screen.getByLabelText("CSV живого опроса") as HTMLInputElement;
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("blocks another selection while reading the file and recovers after validation rejects it", async () => {
  let resolve!: (text: string) => void;
  const file = new File(["invalid"], "answers.csv", { type: "text/csv" });
  Object.defineProperty(file, "text", {
    value: () =>
      new Promise<string>((yes) => {
        resolve = yes;
      }),
  });
  vi.stubGlobal("fetch", () =>
    Promise.resolve(
      new Response(JSON.stringify({ detail: "Строка 2: проверьте решение" }), {
        status: 422,
      }),
    ),
  );
  const input = panel();
  fireEvent.change(input, { target: { files: [file] } });
  expect(input.disabled).toBe(true);
  expect(screen.getByText("Читаем CSV…")).toBeTruthy();
  await act(async () => resolve("invalid"));
  expect(input.disabled).toBe(false);
  expect(screen.getByRole("alert").textContent).toContain("Строка 2");
  expect(screen.queryByText("Читаем CSV…")).toBeNull();
});
it("a file read failure leaves an actionable error and an enabled picker for retry", async () => {
  const file = new File(["contents"], "unreadable.csv", { type: "text/csv" });
  Object.defineProperty(file, "text", {
    value: () => Promise.reject(new Error("read failed")),
  });
  const input = panel();
  await act(async () => fireEvent.change(input, { target: { files: [file] } }));
  expect(input.disabled).toBe(false);
  expect(screen.getByRole("alert").textContent).toContain(
    "Выберите файл ещё раз",
  );
  expect(screen.getByText("unreadable.csv")).toBeTruthy();
});
