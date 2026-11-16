// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Composer from "./Composer";
import ReportHeader from "./features/reports/ReportHeader";
import OriginBanner, {
  hypothesisVerdict,
} from "./features/reports/OriginBanner";
import { draftFromHypothesis, draftFromRecord, runPayload } from "./draft";
import type { Catalog, Experiment } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
const record = sample as unknown as Experiment;
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const hypothesis = {
  lever: "Цена",
  change: "Убрать абонентскую плату",
  variant: "C",
  base_text: record.scenario.variants.C,
  segments: ["senior"],
};
function abRecord(a: number, b: number): Experiment {
  const cell = (yes: number) => ({
    ...record.report.A,
    n: 100,
    yes,
    conversion: yes / 100,
  });
  return {
    ...record,
    id: "child",
    scenario: {
      ...record.scenario,
      variants: { A: "старый", B: "новый" },
      origin: {
        kind: "hypothesis",
        record_id: record.id,
        title: record.scenario.title,
        lever: "Цена",
        change: "Убрать абонентскую плату",
        variant: "C",
      },
    },
    report: { A: cell(a), B: cell(b) },
  };
}
it("links iterations and hypothesis checks to the source study", () => {
  const iteration = runPayload(draftFromRecord(record, true));
  expect(iteration.scenario.origin).toEqual({
    kind: "iteration",
    record_id: record.id,
    title: record.scenario.title,
  });
  const check = runPayload(
    draftFromHypothesis(record, hypothesis, "Новый текст.", true),
  );
  expect(check.scenario.origin).toMatchObject({
    kind: "hypothesis",
    record_id: record.id,
    lever: "Цена",
    variant: "C",
  });
});
it("states whether the hypothesis won and links back", () => {
  expect(hypothesisVerdict(abRecord(40, 41))?.kind).toBe("same");
  expect(hypothesisVerdict(abRecord(40, 30))?.kind).toBe("worse");
  const onOpen = vi.fn(),
    onCompare = vi.fn();
  render(
    <OriginBanner
      record={abRecord(40, 52)}
      stability={{
        leader: "B",
        runner_up: "A",
        share: 0.97,
        level: "stable",
        label: "",
        draws: 4000,
        detail: "",
      }}
      plan={{
        comparisons: [
          {
            pair: ["B", "A"],
            rates: [0.52, 0.4],
            gap_pp: 12,
            n_per_variant: 270,
          },
        ],
        exploratory_n: 30,
        exploratory_detectable_pp: 30,
        focus_segments: [],
        questions: [],
        assumptions: "",
      }}
      onOpen={onOpen}
      onCompare={onCompare}
    />,
  );
  expect(screen.getByText("В симуляции чаще выбирали B")).toBeTruthy();
  expect(screen.getByText(/\+12,0 п\.п\./)).toBeTruthy();
  expect(screen.getByText(/97% повторных выборок/)).toBeTruthy();
  expect(screen.getByText(/≈ 270 оценок/)).toBeTruthy();
  expect(screen.queryByText("Сравнить с исходным")).toBeNull();
  fireEvent.click(screen.getByText("Открыть исходное исследование"));
  expect(onOpen).toHaveBeenCalledWith(record.id);
  cleanup();
  render(
    <OriginBanner
      record={{
        ...record,
        scenario: {
          ...record.scenario,
          origin: { kind: "iteration", record_id: "parent", title: "Исходное" },
        },
      }}
      onCompare={onCompare}
    />,
  );
  expect(screen.getByText(/Основа — исследование «Исходное»/)).toBeTruthy();
  fireEvent.click(screen.getByText("Сравнить с исходным"));
  expect(onCompare).toHaveBeenCalledWith("parent");
});
it("opens survey preparation and reflects a saved survey", () => {
  const onValidation = vi.fn();
  const child = abRecord(40, 40);
  const view = render(
    <OriginBanner record={child} onValidation={onValidation} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Подготовить проверку" }));
  expect(onValidation).toHaveBeenCalledOnce();
  view.rerender(
    <OriginBanner
      record={{
        ...child,
        validation: {
          created_at: "2026-11-13",
          cells: [],
          result: {
            actual_winners: ["A"],
            predicted_winners: ["A"],
            winner_match: null,
            survey_n: 3,
            matched_cells: 1,
            cells: [],
            mae_conversion: 0,
            spearman_variants: null,
          },
        },
      }}
      onValidation={onValidation}
    />,
  );
  expect(screen.getByText(/Сопоставить лидеров пока невозможно/)).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Посмотреть ответы опроса" }),
  );
  expect(onValidation).toHaveBeenCalledTimes(2);
});
it("shows nothing for studies without a source", () => {
  const { container } = render(<OriginBanner record={record} />);
  expect(container.innerHTML).toBe("");
});
it("opens audience review before launching a hypothesis check", () => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const catalog: Catalog = {
    scenarios: { custom: record.scenario },
    segments: {},
  };
  const onRun = vi.fn();
  render(
    <Composer
      catalog={catalog}
      draft={draftFromHypothesis(record, hypothesis, "Новый текст.", true)}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={onRun}
      demo
      busy={false}
    />,
  );
  expect(screen.getByText("Проверка гипотезы «Цена»")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Проверить настройки A/B" }),
  );
  expect(onRun).not.toHaveBeenCalled();
  expect(
    screen.getByRole("region", { name: "Проверьте перед запуском" }),
  ).toBeTruthy();
});

it("discloses corrected probabilities even before insights load", () => {
  const props = {
    base: null,
    onBack: vi.fn(),
    onReuse: vi.fn(),
    onCompare: vi.fn(),
    onExport: vi.fn(),
  };
  const view = render(
    <ReportHeader
      {...props}
      record={{
        ...record,
        report: {
          ...record.report,
          A: { ...record.report.A, inconsistent_n: 7 },
        },
      }}
    />,
  );
  expect(
    screen.getByText("Модель неоднозначно указала вероятность согласия."),
  ).toBeTruthy();
  expect(
    screen.getByLabelText("Корректировки вероятностей по вариантам")
      .textContent,
  ).toContain("Вариант A: 7");
  view.rerender(<ReportHeader {...props} record={record} />);
  expect(
    screen.queryByText("Модель неоднозначно указала вероятность согласия."),
  ).toBeNull();
});
