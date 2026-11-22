import { describe, it, expect } from "vitest";
import {
  draftFromScenario,
  draftFromRecord,
  runPayload,
  draftError,
} from "./draft";
import type { Scenario, Experiment } from "./types";
const scenario: Scenario = {
  title: "Вклад",
  description: "Контекст",
  question: "Откроете?",
  variants: {
    A: "Приложение",
    B: "Отделение",
    C: "Защита",
    D: "Четвёртый",
    E: "Пятый",
  },
  population: { senior: 1 },
  objections: ["неудобно"],
};
describe("research draft contracts", () => {
  it("retains hidden D/E across a reduction without sending them to the run", () => {
    const draft = draftFromScenario(scenario, "custom");
    draft.variantCount = 2;
    expect(Object.keys(runPayload(draft).scenario.variants)).toEqual([
      "A",
      "B",
    ]);
    draft.variantCount = 5;
    expect(runPayload(draft).scenario.variants.E).toBe("Пятый");
    expect(scenario.variants.E).toBe("Пятый");
  });
  it("copies the saved snapshot, preserves imported parameters and enforces demo", () => {
    const record = { scenario, n: 10000, mock: false, seed: 123 } as Experiment;
    const draft = draftFromRecord(record, true);
    draft.variants.A = "Изменено";
    draft.objections.push("дорого");
    expect(draft.n).toBe(10000);
    expect(draft.mock).toBe(true);
    expect(draft.seed).toBe(123);
    expect(scenario.variants.A).toBe("Приложение");
    expect(scenario.objections).toEqual(["неудобно"]);
  });
  it("keeps raw audience weights and refuses empty selected offers or zero audience", () => {
    const draft = draftFromScenario(scenario, "senior_deposit");
    draft.weights = { senior: 37, teen: 63 };
    expect(runPayload(draft).scenario.population).toEqual({
      senior: 37,
      teen: 63,
    });
    draft.variants.B = "  ";
    expect(draftError(draft)).toContain("B");
    draft.variants.B = "Отделение";
    draft.weights = { senior: 0 };
    expect(draftError(draft)).toContain("аудитории");
  });
});

it("keeps the deposit minimum while drafting and submitting a run", () => {
  const source = { ...scenario, deposit_minimum_rub: 50_000 };
  const draft = draftFromScenario(source, "senior_deposit");
  expect(runPayload(draft).scenario.deposit_minimum_rub).toBe(50_000);
  draft.depositMinimumRub = 0;
  expect(draftError(draft)).toMatch(/Минимальный взнос/);
  draft.depositMinimumRub = undefined;
  expect(runPayload(draft).scenario).not.toHaveProperty("deposit_minimum_rub");
});

it.each([
  [Array.from({ length: 13 }, (_, i) => String(i)), /12/],
  [["д".repeat(121)], /120/],
  [["плата", " плата "], /повтор/],
])("catches invalid refusal categories before launch", (objections, error) => {
  const draft = draftFromScenario({ ...scenario, objections }, "custom");
  expect(draftError(draft)).toMatch(error);
});
