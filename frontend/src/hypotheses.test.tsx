// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Hypotheses from "./features/reports/Hypotheses";
import type { Hypothesis } from "./features/reports/types";
import { draftFromHypothesis, runPayload } from "./draft";
import { createBackend } from "./showcase/backend";
import sample from "../../examples/senior-deposit.demo.json";
import type { Experiment } from "./types";
const record = sample as unknown as Experiment;
afterEach(cleanup);
const hypothesis: Hypothesis = {
  id: "h1",
  kind: "objection",
  lever_id: "price",
  lever: "Цена",
  change: "Убрать абонентскую плату",
  variant: "C",
  segments: ["senior"],
  segment_names: ["Пенсионеры 60+"],
  objections: ["плата"],
  evidence: [
    "«плата» — 9 из 30 в сегменте «Пенсионеры 60+»",
    "второй",
    "третий",
    "четвёртый",
  ],
  base_rate: 0.4,
  ceiling_pp: 30,
  audience_pp: 12.5,
  check_n: 120,
  base_text: record.scenario.variants.C,
  proposal: "Новый текст без платы.",
  removed: ["199 ₽/мес"],
  added: ["Без скрытых платежей."],
};
it("shows evidence, the text change, effect ceiling and a test action", () => {
  const onTest = vi.fn();
  render(
    <Hypotheses
      record={record}
      data={{ leader: "C", items: [hypothesis] }}
      onTest={onTest}
    />,
  );
  expect(screen.getByText("Убрать абонентскую плату")).toBeTruthy();
  expect(screen.getByText("до +30,0 п.п.")).toBeTruthy();
  expect(screen.getByText("199 ₽/мес").tagName).toBe("DEL");
  expect(screen.getByText("Без скрытых платежей.").tagName).toBe("INS");
  expect(screen.getByText("Ещё 1")).toBeTruthy();
  expect(screen.getByText("≈ 120 оценок на вариант")).toBeTruthy();
  expect(screen.getByText("Новый текст · черновик по правилу")).toBeTruthy();
  expect(screen.queryByText("Переписать моделью")).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "Проверить: C против гипотезы" }),
  );
  expect(onTest).toHaveBeenCalledWith(hypothesis, "Новый текст без платы.");
});
it("offers LLM rewrite only for LLM studies and explains empty results", () => {
  const { rerender } = render(
    <Hypotheses
      record={{ ...record, mock: false }}
      data={{ leader: "C", items: [hypothesis] }}
    />,
  );
  expect(screen.getByText("Переписать моделью")).toBeTruthy();
  rerender(<Hypotheses record={record} data={{ leader: "C", items: [] }} />);
  expect(screen.getByText(/не найдено/)).toBeTruthy();
});
it("builds an A/B draft on the affected segments", () => {
  const draft = draftFromHypothesis(record, hypothesis, "Новый текст.", true);
  expect(draft.key).toBe("custom");
  expect(draft.variantCount).toBe(2);
  expect(draft.variants).toEqual({
    A: record.scenario.variants.C,
    B: "Новый текст.",
  });
  expect(draft.weights).toEqual({ senior: 100 });
  expect(draft.title).toBe(record.scenario.title + " · гипотеза «Цена»");
  expect(draft.mock).toBe(true);
  expect(draft.description).toBe(
    "Проверка гипотезы «Цена»: A — текущий вариант C, B — убрать абонентскую плату. " +
      record.scenario.description,
  );
  const whole = draftFromHypothesis(
    record,
    { ...hypothesis, segments: [] },
    "x",
  );
  expect(whole.weights).toEqual({ senior: 100 });
});
it("runs a precomputed hypothesis test in the online showcase", async () => {
  const payload = runPayload(
    draftFromHypothesis(record, hypothesis, "Новый текст.", true),
  );
  const run = { ...record, id: "senior_deposit-h1" };
  const api = createBackend({
    session: {},
    catalog: { scenarios: {}, segments: {} },
    sizes: [200],
    seed: 42,
    records: {},
    experiments: [
      {
        scenario: {
          ...payload.scenario,
          population: { senior: 1 },
        },
        n: 200,
        record: run,
      },
    ],
    insights: {},
    estimate: {
      system_chars: 1,
      baseline_chars: 1,
      chars_per_token: 3,
      output_tokens: 1,
      profile_chars: 1,
      latency_s: 1,
    },
    templates: {},
  });
  expect((await api("POST", "/runs", payload)).status).toBe(200);
  expect((await api("POST", "/runs", { ...payload, n: 100 })).status).toBe(422);
  const rewrite = await api("POST", "/hypotheses/rewrite", {});
  expect(rewrite.status).toBe(422);
});
