// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ReportHeader from "./features/reports/ReportHeader";
import type { Experiment } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
afterEach(cleanup);
function show(record: Experiment, pending?: string) {
  const actions = {
    onBack: vi.fn(),
    onReuse: vi.fn(),
    onCompare: vi.fn(),
    onExport: vi.fn(),
    onValidation: vi.fn(),
    onRetry: vi.fn(),
  };
  render(
    <ReportHeader record={record} base={null} pending={pending} {...actions} />,
  );
  return actions;
}
const record = () => structuredClone(sample) as unknown as Experiment;
it("offers survey preparation with an explicit demo boundary", () => {
  const a = show(record());
  fireEvent.click(
    screen.getByRole("button", { name: "Открыть пример живой проверки" }),
  );
  expect(a.onValidation).toHaveBeenCalledOnce();
  expect(screen.getByText(/Демо показывает процесс/)).toBeTruthy();
});
it("prioritizes missing variant data over an uploaded survey", () => {
  const r = record();
  r.report.A.n = 0;
  r.report.A.failed_n = r.n;
  const a = show(r);
  fireEvent.click(
    screen.getByRole("button", { name: "Проверить настройки запуска" }),
  );
  expect(a.onReuse).toHaveBeenCalledOnce();
  expect(screen.getByText(/не у всех предложений/)).toBeTruthy();
});
it("prioritizes unsaved archive recovery over another model run", () => {
  const a = show(record(), "storage unavailable");
  const region = screen.getByRole("region", {
    name: "Следующий шаг исследования",
  });
  fireEvent.click(region.querySelector("button")!);
  expect(a.onRetry).toHaveBeenCalledOnce();
  expect(a.onReuse).not.toHaveBeenCalled();
});
it("routes complete LLM results to survey and uploaded results to discrepancies", () => {
  const r = record();
  r.mock = false;
  const a = show(r);
  fireEvent.click(
    screen.getByRole("button", { name: "Подготовить живую проверку" }),
  );
  expect(a.onValidation).toHaveBeenCalledOnce();
  cleanup();
  r.validation = {
    created_at: "2026-11-16",
    cells: [],
    result: {
      survey_n: 6,
      matched_cells: 1,
      cells: [],
      actual_winners: [],
      predicted_winners: [],
      winner_match: null,
      mae_conversion: 0,
      spearman_variants: null,
    },
  };
  const b = show(r);
  fireEvent.click(
    screen.getByRole("button", { name: "Разобрать расхождения с опросом" }),
  );
  expect(b.onValidation).toHaveBeenCalledOnce();
  expect(screen.getByText(/Подлинность и сопоставимость/)).toBeTruthy();
});

it("requires coverage of every selected segment even when each variant has answers", () => {
  const r = record();
  r.mock = false;
  r.scenario.population = { ...r.scenario.population, student_msk: 1 };
  const a = show(r);
  fireEvent.click(
    screen.getByRole("button", { name: "Проверить настройки запуска" }),
  );
  expect(a.onReuse).toHaveBeenCalledOnce();
});
