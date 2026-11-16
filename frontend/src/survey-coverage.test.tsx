// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import SurveyCoverage from "./features/reports/SurveyCoverage";
import type { Experiment, ValidationResult } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
afterEach(cleanup);
const record = () =>
  ({
    ...structuredClone(sample),
    scenario: {
      ...sample.scenario,
      population: { senior: 0.5, student_msk: 0.5 },
      variants: { A: "A", B: "B" },
    },
    report: { A: sample.report.A, B: sample.report.B },
  }) as unknown as Experiment;
function result(cells: [string, string, number][]): ValidationResult {
  return {
    cells: cells.map(([variant, segment, survey_n]) => ({
      variant,
      segment,
      survey_n,
      actual: 0.5,
      predicted: 0.4,
      error: 0.1,
    })),
    survey_n: cells.reduce((s, c) => s + c[2], 0),
    matched_cells: cells.length,
    mae_conversion: 0.1,
    spearman_variants: null,
    winner_match: null,
    actual_winners: [],
    predicted_winners: [],
  };
}
it("makes missing variants and segment cells visible before interpreting metrics", () => {
  render(
    <SurveyCoverage
      record={record()}
      result={result([["A", "senior", 3]])}
      segments={{}}
    />,
  );
  expect(screen.getByText("1 из 4 пар «предложение — сегмент»")).toBeTruthy();
  expect(screen.getByText(/Нет оценок предложений: B/)).toBeTruthy();
  expect(screen.getByRole("cell", { name: /^Нет ответов$/ })).toBeTruthy();
});
it("warns when audiences differ despite equal total counts", () => {
  render(
    <SurveyCoverage
      record={record()}
      result={result([
        ["A", "senior", 9],
        ["A", "student_msk", 1],
        ["B", "senior", 1],
        ["B", "student_msk", 9],
      ])}
      segments={{}}
    />,
  );
  expect(screen.getByText(/Состав аудитории различается/)).toBeTruthy();
});
it("recognizes equal proportions with different sample sizes without claiming validity", () => {
  render(
    <SurveyCoverage
      record={record()}
      result={result([
        ["A", "senior", 2],
        ["A", "student_msk", 2],
        ["B", "senior", 4],
        ["B", "student_msk", 4],
      ])}
      segments={{}}
    />,
  );
  expect(screen.getByText(/Доли сегментов одинаковы/)).toBeTruthy();
  expect(screen.getByText(/не подтверждает репрезентативность/)).toBeTruthy();
});
it("excludes zero-weight segments from expected coverage", () => {
  const r = record();
  r.scenario.population.student_msk = 0;
  render(
    <SurveyCoverage
      record={r}
      result={result([
        ["A", "senior", 2],
        ["B", "senior", 2],
      ])}
      segments={{}}
    />,
  );
  expect(screen.getByText("2 из 2 пар «предложение — сегмент»")).toBeTruthy();
});
