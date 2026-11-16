// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ReportHeader from "./features/reports/ReportHeader";
import type { Experiment } from "./types";
import sample from "../../examples/senior-deposit.demo.json";

afterEach(cleanup);

it("shows original and corrected means and identifies missing historical values", () => {
  const record = structuredClone(sample) as unknown as Experiment;
  record.report.A = {
    ...record.report.A,
    inconsistent_n: 7,
    raw_probability: { mean: 0.8, sd: 0.1, n: record.report.A.n },
    probability: { mean: 0.4, sd: 0.3, n: record.report.A.n },
  };
  const props = {
    record,
    base: null,
    onBack: vi.fn(),
    onReuse: vi.fn(),
    onCompare: vi.fn(),
    onExport: vi.fn(),
  };
  const view = render(<ReportHeader {...props} />);
  const warning = () =>
    screen.getByLabelText("Корректировки вероятностей по вариантам")
      .textContent;
  expect(warning()).toMatch(/до корректировки: 80[,.]0?\s?%/);
  expect(warning()).toMatch(/после: 40[,.]0?\s?%/);
  delete record.report.A.raw_probability;
  view.rerender(<ReportHeader {...props} />);
  expect(warning()).toContain("Исходные значения не сохранены");
  expect(warning()).not.toContain("до корректировки: 80");
});
