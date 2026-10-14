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
import type { Catalog, Experiment } from "./types";
const record = sample as unknown as Experiment;
const catalog: Catalog = { scenarios: {}, segments: {} };
function panel(value = record) {
  return render(
    <ValidationPanel
      record={value}
      catalog={catalog}
      onUpdated={() => {}}
      onExport={() => {}}
    />,
  );
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("keeps the questionnaire neutral and uses the actual saved question and offers", () => {
  panel({
    ...record,
    scenario: {
      ...record.scenario,
      question: "Открыли бы вы счёт на этих условиях?",
      description: "INTERNAL-DESCRIPTION",
    },
  });
  fireEvent.click(screen.getByText("Посмотреть анкету и коды сегментов"));
  expect(screen.getByText("Открыли бы вы счёт на этих условиях?")).toBeTruthy();
  for (const text of Object.values(record.scenario.variants)) {
    expect(screen.getByText(text)).toBeTruthy();
  }
  expect(screen.queryByText("INTERNAL-DESCRIPTION")).toBeNull();
  expect(screen.queryByText(/Лидер симуляции/)).toBeNull();
});
it("disables duplicate kit downloads until the session-bound export is ready", async () => {
  let resolve!: (response: Response) => void;
  vi.stubGlobal("fetch", (path: string, options: RequestInit) => {
    expect(path).toBe("/api/export");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body as string)).toEqual({
      record_id: record.id,
      kind: "survey-kit",
      format: "zip",
    });
    return new Promise<Response>((yes) => {
      resolve = yes;
    });
  });
  let target = "";
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    target = this.href;
  });
  panel();
  fireEvent.click(
    screen.getByRole("button", { name: "Скачать комплект опроса" }),
  );
  expect(
    (
      screen.getByRole("button", {
        name: "Готовим комплект…",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  await act(async () =>
    resolve(new Response(JSON.stringify({ url: "/download/test-kit" }))),
  );
  expect(target.endsWith("/download/test-kit")).toBe(true);
  expect(
    (
      screen.getByRole("button", {
        name: "Скачать комплект опроса",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(false);
});
it("shows download errors and allows a clean retry without altering survey state", async () => {
  let failed = true;
  vi.stubGlobal("fetch", () =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          failed
            ? { detail: "Архив временно недоступен" }
            : { url: "/download/retry-kit" },
        ),
        { status: failed ? 503 : 200 },
      ),
    ),
  );
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  panel();
  await act(async () =>
    fireEvent.click(
      screen.getByRole("button", { name: "Скачать комплект опроса" }),
    ),
  );
  expect(screen.getByText("Архив временно недоступен")).toBeTruthy();
  failed = false;
  await act(async () =>
    fireEvent.click(
      screen.getByRole("button", { name: "Скачать комплект опроса" }),
    ),
  );
  expect(screen.queryByText("Архив временно недоступен")).toBeNull();
  expect(screen.getByLabelText("CSV живого опроса")).toBeTruthy();
});
it("explains unavailable comparison coverage instead of offering a useless kit", () => {
  const empty = structuredClone(record);
  for (const report of Object.values(empty.report))
    for (const cell of Object.values(report.segments)) cell.n = 0;
  panel(empty);
  expect(
    (
      screen.getByRole("button", {
        name: "Скачать комплект опроса",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(
    screen.getByText(/Нет валидных ответов симуляции для сопоставления/),
  ).toBeTruthy();
});
