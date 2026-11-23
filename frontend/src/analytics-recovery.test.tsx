// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ReportPage from "./features/reports/ReportPage";
import type { Insights } from "./features/reports/types";
import type { Experiment } from "./types";
import { api } from "./api";
import sample from "../../examples/senior-deposit.demo.json";
const record = sample as unknown as Experiment;
const ready: Insights = {
  report: record.report,
  summary: { leaders: ["C"], best: 0.555, gap_pp: 12.5, failed_n: 0 },
  quality: {
    kind: "demo",
    title: "Демонстрация процесса",
    detail: "Синтетические ответы",
  },
  stability: null,
  baseline: null,
  hypotheses: { leader: "C", items: [] },
  plan: {
    comparisons: [],
    exploratory_n: 30,
    exploratory_detectable_pp: 34.3,
    focus_segments: [],
    questions: [],
    assumptions: "Ориентир",
  },
};
function show(value = record) {
  return render(
    <ReportPage
      record={value}
      catalog={{ scenarios: {}, segments: {} }}
      onBack={() => {}}
      onReuse={() => {}}
      onUpdated={() => {}}
      onCompare={() => {}}
      onError={() => {}}
    />,
  );
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it("focuses the survey plan when opening an unvalidated report from its main action", async () => {
  vi.spyOn(api, "request").mockImplementation(<T,>() =>
    Promise.resolve(ready as T),
  );
  show();
  await act(async () => {});
  const action = screen.getByRole("button", {
    name: "Открыть пример живой проверки",
  });
  action.focus();
  fireEvent.click(action);
  const heading = screen.getByRole("heading", { name: "Спланируйте проверку" });
  expect(document.activeElement).toBe(heading);
  expect(
    screen
      .getByRole("tab", { name: "Проверка опросом" })
      .getAttribute("aria-selected"),
  ).toBe("true");
});
it("moves focus directly to saved discrepancies from the report action", async () => {
  vi.spyOn(api, "request").mockImplementation(<T,>() =>
    Promise.resolve(ready as T),
  );
  show({
    ...record,
    mock: false,
    validation: {
      created_at: record.created_at,
      cells: [],
      result: {
        mae_conversion: 0.2,
        spearman_variants: null,
        winner_match: null,
        survey_n: 6,
        matched_cells: 1,
        cells: [],
        actual_winners: [],
        predicted_winners: [],
      },
    },
  });
  await act(async () => {});
  fireEvent.click(
    screen.getByRole("button", { name: "Разобрать расхождения с опросом" }),
  );
  const heading = screen.getByRole("heading", {
    name: "Расхождения по сегментам",
  });
  expect(document.activeElement).toBe(heading);
  const overview = screen.getByRole("tab", { name: "Результат" });
  overview.focus();
  fireEvent.click(overview);
  const validation = screen.getByRole("tab", { name: "Проверка опросом" });
  validation.focus();
  fireEvent.click(validation);
  expect(document.activeElement).toBe(validation);
});
it("does not label pending analysis as absence of valid answers", async () => {
  const loading = deferred<Insights>();
  vi.spyOn(api, "request").mockImplementation(
    <T,>() => loading.promise as Promise<T>,
  );
  show();
  expect(document.querySelector(".report-summary")!.textContent).not.toContain(
    "Нет валидных ответов",
  );
  await act(async () => loading.resolve(ready));
  expect(screen.getByText("Лидер симуляции")).toBeTruthy();
});
it("stops loading after an error and recovers without rerunning a model", async () => {
  let fail = true;
  const request = vi
    .spyOn(api, "request")
    .mockImplementation(<T,>(path: string) => {
      if (path !== "/insights")
        throw new Error("Unexpected operation: " + path);
      return (
        fail
          ? Promise.reject(new Error("Сеть недоступна"))
          : Promise.resolve(ready)
      ) as Promise<T>;
    });
  show();
  await act(async () => {});
  expect(screen.getByRole("alert").textContent).toContain("Сеть недоступна");
  expect(document.querySelector(".report-summary")!.textContent).not.toContain(
    "Нет валидных ответов",
  );
  expect(document.querySelector('[aria-busy="true"]')).toBeNull();
  expect(screen.queryAllByText(/Готовим (разбор|план|гипотезы)/)).toHaveLength(
    0,
  );
  fireEvent.click(screen.getByRole("tab", { name: "Гипотезы" }));
  expect(screen.queryByText("Готовим гипотезы…")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "Проверка опросом" }));
  expect(screen.queryByText("Готовим план…")).toBeNull();
  expect(
    (
      screen.getByRole("button", {
        name: "Скачать комплект опроса",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(false);
  fail = false;
  fireEvent.click(
    screen.getByRole("button", { name: "Повторить загрузку аналитики" }),
  );
  await act(async () => {});
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByText("Лидер симуляции")).toBeTruthy();
  expect(request.mock.calls.every(([path]) => path === "/insights")).toBe(true);
});
it("keeps global analysis ready when a segment fails and retries only the segment", async () => {
  let failSegment = true;
  const request = vi
    .spyOn(api, "request")
    .mockImplementation(
      <T,>(path: string, _method?: string, body?: unknown) => {
        if (path !== "/insights") throw new Error("Unexpected operation");
        const segment = (body as { segment: string }).segment;
        return (
          segment !== "all" && failSegment
            ? Promise.reject(new Error("Сегмент временно недоступен"))
            : Promise.resolve(ready)
        ) as Promise<T>;
      },
    );
  show();
  await act(async () => {});
  fireEvent.change(
    screen.getByRole("combobox", { name: "Разобрать аудиторию" }),
    { target: { value: "senior" } },
  );
  await act(async () => {});
  expect(screen.getByText("Лидер симуляции")).toBeTruthy();
  expect(
    screen.queryByRole("img", {
      name: "Доля согласий и 95-процентные интервалы симуляции",
    }),
  ).toBeNull();
  expect(screen.getByRole("alert").textContent).toContain(
    "Сегмент временно недоступен",
  );
  expect(document.querySelector('[aria-busy="true"]')).toBeNull();
  const before = request.mock.calls.filter(
    ([, , body]) => (body as { segment: string }).segment === "all",
  ).length;
  failSegment = false;
  fireEvent.click(
    screen.getByRole("button", { name: "Повторить загрузку аналитики" }),
  );
  await act(async () => {});
  expect(screen.queryByRole("alert")).toBeNull();
  expect(
    screen.getByRole("img", {
      name: "Доля согласий и 95-процентные интервалы симуляции",
    }),
  ).toBeTruthy();
  expect(
    request.mock.calls.filter(
      ([, , body]) => (body as { segment: string }).segment === "all",
    ),
  ).toHaveLength(before);
});
it("still explains a successful analysis with no valid answers", async () => {
  vi.spyOn(api, "request").mockImplementation(
    <T,>() =>
      Promise.resolve({
        ...ready,
        summary: { leaders: [], best: 0, gap_pp: 0, failed_n: 600 },
      }) as Promise<T>,
  );
  show();
  await act(async () => {});
  expect(document.querySelector(".report-summary")!.textContent).toContain(
    "Нет валидных ответов",
  );
});
it("ignores a late segment error after returning to the whole audience", async () => {
  const segment = deferred<Insights>();
  vi.spyOn(api, "request").mockImplementation(
    <T,>(_path: string, _method?: string, body?: unknown) =>
      ((body as { segment: string }).segment === "all"
        ? Promise.resolve(ready)
        : segment.promise) as Promise<T>,
  );
  show();
  await act(async () => {});
  fireEvent.change(
    screen.getByRole("combobox", { name: "Разобрать аудиторию" }),
    { target: { value: "senior" } },
  );
  await act(async () => {});
  fireEvent.change(
    screen.getByRole("combobox", { name: "Разобрать аудиторию" }),
    { target: { value: "all" } },
  );
  await act(async () => segment.reject(new Error("Устаревшая ошибка")));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(
    screen.getByRole("img", {
      name: "Доля согласий и 95-процентные интервалы симуляции",
    }),
  ).toBeTruthy();
});
