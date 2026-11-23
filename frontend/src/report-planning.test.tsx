// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import LivePlan from "./features/reports/LivePlan";
import BaselineCard from "./features/reports/BaselineCard";
import ValidationMetrics from "./features/reports/ValidationMetrics";
import { decimal, percent } from "./components";
import sample from "../../examples/senior-deposit.demo.json";
import type { Experiment, ValidationResult } from "./types";
const record = sample as unknown as Experiment;
afterEach(cleanup);
it("formats shares with one decimal comma everywhere", () => {
  expect(percent(0.555)).toBe("55,5%");
  expect(percent(0.045)).toBe("4,5%");
  expect(percent(null)).toBe("—");
  expect(decimal(-1.25)).toBe("−1,3");
});
it("shows sample size, exploratory limit and interview questions", () => {
  render(
    <LivePlan
      mock
      plan={{
        comparisons: [
          {
            pair: ["C", "B"],
            rates: [0.555, 0.43],
            gap_pp: 12.5,
            n_per_variant: 250,
          },
          {
            pair: ["C", "A"],
            rates: [0.555, 0.5501],
            gap_pp: 0.49,
            n_per_variant: null,
          },
        ],
        exploratory_n: 30,
        exploratory_detectable_pp: 34.3,
        focus_segments: [],
        questions: [
          { text: "Вспомните последний раз?", source: "общий вопрос" },
        ],
        assumptions: "α = 0,05",
      }}
    />,
  );
  expect(screen.getByText("≈ 250")).toBeTruthy();
  expect(screen.getByText("без расчёта при разнице < 2 п.п.")).toBeTruthy();
  expect(screen.getByText("34,3 п.п.")).toBeTruthy();
  expect(screen.getByText("Вспомните последний раз?")).toBeTruthy();
  expect(screen.getByText(/механизм планирования/)).toBeTruthy();
});
it("compares twins with the simple approach and warns about homogeneous LLM answers", () => {
  const llm: Experiment = {
    ...record,
    mock: false,
    report: {
      ...record.report,
      A: { ...record.report.A, probability: { mean: 0.5, sd: 0.01, n: 200 } },
    },
  };
  render(
    <BaselineCard
      record={llm}
      baseline={{
        method: "single_prompt",
        rows: [
          { variant: "A", twins: 0.045, baseline: 0.3 },
          { variant: "C", twins: 0.555, baseline: 0.4 },
        ],
        same_leader: false,
        twin_leaders: ["C"],
        baseline_leaders: ["B"],
        spearman: 0.5,
      }}
    />,
  );
  expect(screen.getByText("Лидеры различаются")).toBeTruthy();
  expect(screen.getByText("−25,5 п.п.")).toBeTruthy();
  expect(screen.getByText(/Ответы персонажей однородны/)).toBeTruthy();
});
it("keeps the run usable when the simple approach failed", () => {
  render(
    <BaselineCard
      record={record}
      baseline={{
        method: "single_prompt",
        error: "Запрос к модели не выполнен.",
      }}
    />,
  );
  expect(screen.getByText(/Простой подход не дал оценку/)).toBeTruthy();
  expect(screen.queryByText(/однородны/)).toBeNull();
});
it("reports which approach was closer to the survey", () => {
  const result: ValidationResult = {
    mae_conversion: 0.155,
    spearman_variants: 0.5,
    winner_match: false,
    survey_n: 120,
    matched_cells: 3,
    cells: [],
    actual_winners: ["B"],
    predicted_winners: ["C"],
    baseline: {
      twins_mae_variants: 0.155,
      baseline_mae_variants: 0.08,
      twins_spearman: 0.5,
      baseline_spearman: 1,
      baseline_winner_match: false,
      variants: [],
    },
  };
  render(<ValidationMetrics result={result} segments={{}} />);
  expect(screen.getByText("Простой подход")).toBeTruthy();
  expect(screen.getByText("8,0")).toBeTruthy();
});

it("explains why the survey ranking is unavailable and retains segment-level errors", () => {
  const result: ValidationResult = {
    ranking_unavailable: "different_mix",
    mae_conversion: 0.1,
    spearman_variants: null,
    winner_match: null,
    survey_n: 12,
    matched_cells: 1,
    cells: [
      {
        variant: "A",
        segment: "senior",
        survey_n: 12,
        actual: 0.5,
        predicted: 0.4,
        error: 0.1,
      },
    ],
    actual_winners: [],
    predicted_winners: [],
  };
  render(<ValidationMetrics result={result} segments={{}} />);
  expect(screen.getByText("Общий рейтинг недоступен.")).toBeTruthy();
  expect(screen.getByText(/Доли сегментов отличаются/)).toBeTruthy();
  expect(screen.getByText("50,0%")).toBeTruthy();
  expect(screen.getByText("40,0%")).toBeTruthy();
  expect(screen.queryByText("Кто ближе к опросу")).toBeNull();
});

it("orders discrepancies by absolute size and shows direction with the response count", () => {
  const result: ValidationResult = {
    mae_conversion: 0.2,
    spearman_variants: null,
    winner_match: null,
    survey_n: 31,
    matched_cells: 3,
    cells: [
      {
        variant: "A",
        segment: "senior",
        survey_n: 15,
        actual: 0.5,
        predicted: 0.4,
        error: 0.1,
      },
      {
        variant: "B",
        segment: "senior",
        survey_n: 1,
        actual: 0,
        predicted: 0.5,
        error: 0.5,
      },
      {
        variant: "C",
        segment: "senior",
        survey_n: 15,
        actual: 0.7,
        predicted: 0.2,
        error: 0.5,
      },
    ],
    actual_winners: [],
    predicted_winners: [],
  };
  render(<ValidationMetrics result={result} segments={{}} />);
  const [, first, second, third] = screen.getAllByRole("row");
  expect(within(first).getByText("C")).toBeTruthy();
  expect(within(first).getByText("15")).toBeTruthy();
  expect(within(first).getByText("Модель ниже")).toBeTruthy();
  expect(within(second).getByText("B")).toBeTruthy();
  expect(within(second).getByText("1")).toBeTruthy();
  expect(within(second).getByText("Модель выше")).toBeTruthy();
  expect(within(third).getByText("A")).toBeTruthy();
  expect(result.cells.map((cell) => cell.variant)).toEqual(["A", "B", "C"]);
  const comparison = screen.getByRole("region", {
    name: "Сравнение предложений в сегменте",
  });
  expect(within(comparison).getByText("Разница A − B")).toBeTruthy();
  expect(within(comparison).getByText("+50,0 п.п.")).toBeTruthy();
  expect(within(comparison).getByText("−10,0 п.п.")).toBeTruthy();
  fireEvent.change(
    within(comparison).getByRole("combobox", { name: "Пара для сравнения" }),
    {
      target: { value: "B-C" },
    },
  );
  expect(within(comparison).getByText("Разница B − C")).toBeTruthy();
  expect(within(comparison).getByText("−70,0 п.п.")).toBeTruthy();
  expect(within(comparison).getByText("+30,0 п.п.")).toBeTruthy();
  expect(within(comparison).getByText("B — 1 оценка")).toBeTruthy();
  expect(within(comparison).getByText("C — 15 оценок")).toBeTruthy();
});

it("filters discrepancies to one segment and preserves the full-survey metrics", () => {
  const result: ValidationResult = {
    ranking_unavailable: "different_mix",
    mae_conversion: 0.2,
    spearman_variants: null,
    winner_match: null,
    survey_n: 25,
    matched_cells: 3,
    cells: [
      {
        variant: "A",
        segment: "senior",
        survey_n: 10,
        actual: 0.5,
        predicted: 0.4,
        error: 0.1,
      },
      {
        variant: "B",
        segment: "senior",
        survey_n: 10,
        actual: 0.7,
        predicted: 0.4,
        error: 0.3,
      },
      {
        variant: "C",
        segment: "teen",
        survey_n: 5,
        actual: 0.2,
        predicted: 0.4,
        error: 0.2,
      },
    ],
    actual_winners: [],
    predicted_winners: [],
  };
  const { rerender } = render(
    <ValidationMetrics result={result} segments={{}} />,
  );
  const selector = screen.getByRole("combobox", { name: "Сегмент в таблице" });
  const table = screen.getByRole("region", { name: "Таблица расхождений" });
  expect(
    screen.queryByRole("region", { name: "Сравнение предложений в сегменте" }),
  ).toBeNull();
  fireEvent.change(selector, { target: { value: "senior" } });
  expect(within(table).getAllByRole("row")).toHaveLength(3);
  expect(within(table).queryByText("teen")).toBeNull();
  expect(screen.getByText("Показано 2 из 3 пар")).toBeTruthy();
  expect(screen.getByText("20,0")).toBeTruthy();
  const comparison = screen.getByRole("region", {
    name: "Сравнение предложений в сегменте",
  });
  expect(within(comparison).getByText("−20,0 п.п.")).toBeTruthy();
  expect(within(comparison).getByText("0,0 п.п.")).toBeTruthy();
  fireEvent.change(selector, { target: { value: "teen" } });
  expect(within(table).getAllByRole("row")).toHaveLength(2);
  expect(screen.getByText(/оценивали только одно предложение/)).toBeTruthy();
  expect(
    screen.queryByRole("region", { name: "Сравнение предложений в сегменте" }),
  ).toBeNull();
  rerender(
    <ValidationMetrics
      result={{ ...result, cells: result.cells.slice(0, 2) }}
      segments={{}}
    />,
  );
  expect(
    screen.queryByRole("combobox", { name: "Сегмент в таблице" }),
  ).toBeNull();
  expect(within(table).getAllByRole("row")).toHaveLength(3);
});
