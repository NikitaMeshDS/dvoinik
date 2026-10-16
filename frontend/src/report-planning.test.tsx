// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
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
  expect(screen.getByText("не различить")).toBeTruthy();
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
