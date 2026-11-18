// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
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

const savedValidation = {
  created_at: "2026-11-10T12:00:00Z",
  cells: [],
  result: {
    survey_n: 20,
    matched_cells: 2,
    mae_conversion: 0.1,
    spearman_variants: null,
    winner_match: null,
    cells: [],
    actual_winners: [],
    predicted_winners: [],
  },
};
async function replacementPanel(failSave = false) {
  const original = { ...record, validation: savedValidation };
  const next = {
    ...original,
    validation: {
      ...savedValidation,
      result: { ...savedValidation.result, survey_n: 30 },
    },
  };
  const updated = vi.fn(),
    exported = vi.fn(),
    dirty = vi.fn();
  vi.spyOn(api, "request").mockImplementation(
    <T,>(_path: string, method?: string) => {
      if (method === "PUT")
        return (
          failSave
            ? Promise.reject(new Error("Проверка уже изменена"))
            : Promise.resolve(next)
        ) as Promise<T>;
      return Promise.resolve({
        record: next,
        base_validation: savedValidation,
        preview_id: "preview-one",
      }) as Promise<T>;
    },
  );
  render(
    <ValidationPanel
      record={original}
      catalog={{ scenarios: {}, segments: {} }}
      onUpdated={updated}
      onExport={exported}
      onDirtyChange={dirty}
    />,
  );
  const file = new File(["test"], "answers.csv");
  Object.defineProperty(file, "text", { value: () => Promise.resolve("test") });
  await act(async () =>
    fireEvent.change(screen.getByLabelText("CSV живого опроса"), {
      target: { files: [file] },
    }),
  );
  return { original, updated, exported, dirty };
}
it("makes replacement explicit, offers the saved snapshot and can discard without changing it", async () => {
  const { original, updated, exported } = await replacementPanel();
  expect(screen.getByText(/Было: 20 оценок/)).toBeTruthy();
  expect(screen.getByText(/Будет: 30 оценок/)).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "Заменить проверку" }),
  ).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Скачать сохранённый снимок" }),
  );
  expect(exported).toHaveBeenCalledWith("json");
  fireEvent.click(
    screen.getByRole("button", { name: "Отменить предпросмотр" }),
  );
  expect(screen.queryByText("Предпросмотр · ещё не сохранён")).toBeNull();
  expect(updated).not.toHaveBeenCalled();
  expect(original.validation.result.survey_n).toBe(20);
});
it("retains replacement preview on a conflicting save and clears it only after success", async () => {
  const { updated } = await replacementPanel(true);
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Заменить проверку" })),
  );
  expect(screen.getByRole("alert").textContent).toContain(
    "Проверка уже изменена",
  );
  expect(screen.getByText("Предпросмотр · ещё не сохранён")).toBeTruthy();
  expect(updated).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("status", { name: "Проверка сохранена" }),
  ).toBeNull();
});

it("clears the dirty preview after a successful save", async () => {
  const { updated, dirty } = await replacementPanel();
  expect(dirty).toHaveBeenLastCalledWith(true);
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Заменить проверку" })),
  );
  expect(updated.mock.calls[0][0].validation.result.survey_n).toBe(30);
  expect(screen.queryByText("Предпросмотр · ещё не сохранён")).toBeNull();
  expect(dirty).toHaveBeenLastCalledWith(false);
});

it("announces a persisted survey and keeps save actions after the metrics", async () => {
  await replacementPanel();
  const button = screen.getByRole("button", { name: "Заменить проверку" });
  const table = document.querySelector(".survey-results .data-table")!;
  expect(
    table.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  await act(async () => fireEvent.click(button));
  expect(
    screen.getByRole("status", { name: "Проверка сохранена" }).textContent,
  ).toContain("30 оценок");
  const savedMessage = screen.getByRole("status", {
    name: "Проверка сохранена",
  });
  const savedTable = document.querySelector(".survey-results .data-table")!;
  expect(
    savedTable.compareDocumentPosition(savedMessage) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});
