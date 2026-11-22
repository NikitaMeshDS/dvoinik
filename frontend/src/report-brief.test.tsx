// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ReportHeader from "./features/reports/ReportHeader";
import type { Insights } from "./features/reports/types";
import type { Experiment } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
const record = sample as unknown as Experiment;
const base: Insights = {
  report: record.report,
  summary: { leaders: ["C"], best: 0.555, gap_pp: 12.5, failed_n: 0 },
  quality: { kind: "demo", title: "Демо", detail: "По правилам" },
  stability: null,
};
afterEach(cleanup);
function show(r = record, insight: Insights | null = base, pending?: string) {
  const onValidation = vi.fn(),
    onRetry = vi.fn();
  render(
    <ReportHeader
      record={r}
      base={insight}
      pending={pending}
      onBack={() => {}}
      onReuse={() => {}}
      onCompare={() => {}}
      onExport={() => {}}
      onValidation={onValidation}
      onRetry={onRetry}
    />,
  );
  return { onValidation, onRetry };
}
it("summarizes the actual question and observed simulation separately from the next action", () => {
  const { onValidation } = show();
  const brief = screen.getByRole("region", {
    name: "Краткий итог исследования",
  });
  expect(within(brief).getByText(record.scenario.question)).toBeTruthy();
  expect(within(brief).getByText(record.scenario.variants.A)).toBeTruthy();
  expect(within(brief).getByText(/55,5%/)).toBeTruthy();
  const sources = within(brief).getByRole("group", {
    name: "Источники данных",
  });
  expect(within(sources).getByText("Эвристическое демо")).toBeTruthy();
  expect(within(sources).getByText("Опрос ещё не загружен")).toBeTruthy();
  expect(within(brief).getByText(/выше следующего на 12,5 п. п./)).toBeTruthy();
  expect(within(brief).getByText(/не прогноз спроса/)).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", {
      name: "Открыть пример живой проверки",
    }),
  );
  expect(onValidation).toHaveBeenCalledOnce();
});
it("separates the model result from a partially covered survey in the first screen", () => {
  const r = {
    ...record,
    mock: false,
    model: "qwen-local",
    validation: {
      created_at: "2026-11-22",
      cells: [{ variant: "A", segment: "senior", n: 6, yes: 2 }],
      result: {
        survey_n: 6,
        matched_cells: 1,
        cells: [],
        actual_winners: [],
        predicted_winners: [],
        winner_match: null,
        mae_conversion: 0.2,
        spearman_variants: null,
      },
    },
  };
  show(r);
  const sources = screen.getByRole("group", { name: "Источники данных" });
  expect(within(sources).getByText("Симуляция модели")).toBeTruthy();
  expect(within(sources).getByText("qwen-local")).toBeTruthy();
  expect(within(sources).getByText("Неполное покрытие опроса")).toBeTruthy();
  expect(within(sources).getByText(/6 оценок · 1 из 3 пар/)).toBeTruthy();
});
it("prioritizes an unsaved result in the brief rather than offering another run", () => {
  const { onRetry } = show(record, base, "Диск недоступен");
  fireEvent.click(screen.getByRole("button", { name: "Повторить сохранение" }));
  expect(onRetry).toHaveBeenCalledOnce();
});
it("does not present a leader when analysis is unavailable", () => {
  show(record, null);
  const brief = screen.getByRole("region", {
    name: "Краткий итог исследования",
  });
  expect(within(brief).queryByText(/55,5%/)).toBeNull();
  expect(within(brief).getByText(/Загружаем/)).toBeTruthy();
});
it.each(["failed", "missing"])(
  "keeps quality limits visible while an unsaved %s result prioritizes saving",
  (issue) => {
    const r = structuredClone(record);
    if (issue === "failed") r.report.A.failed_n = 1;
    else delete r.report.A.segments[Object.keys(r.scenario.population)[0]];
    show(r, base, "Диск недоступен");
    const brief = screen.getByRole("region", {
      name: "Краткий итог исследования",
    });
    expect(within(brief).queryByText(/55,5%/)).toBeNull();
    expect(within(brief).getByText(/Проверьте качество/)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Повторить сохранение" }),
    ).toBeTruthy();
  },
);
