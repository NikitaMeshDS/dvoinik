// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import sample from "../../examples/senior-deposit.demo.json";
import Overview from "./features/reports/Overview";
import type { Catalog, Experiment } from "./types";

afterEach(cleanup);
const saved = sample as unknown as Experiment;
const catalog: Catalog = { scenarios: {}, segments: {} };

function show(record: Experiment) {
  render(
    <Overview
      record={record}
      catalog={catalog}
      focus={null}
      segment="all"
      setSegment={() => {}}
      variant="A"
      setVariant={() => {}}
    />,
  );
}

it("shows interest separately from financial eligibility", () => {
  show({
    ...saved,
    scenario: { ...saved.scenario, deposit_minimum_rub: 50_000 },
    deposit_eligibility: { available_n: 100, unavailable_n: 90, unknown_n: 10 },
  });
  expect(
    screen.getByRole("heading", { name: "Интерес к предложению" }),
  ).toBeTruthy();
  const gate = screen.getByRole("region", { name: "По минимальному взносу" });
  expect(within(gate).getByText(/100 из 200/)).toBeTruthy();
  expect(within(gate).getByText(/Сумма неизвестна у 10/)).toBeTruthy();
});

it("keeps historical reports without eligibility readable", () => {
  show(saved);
  expect(
    screen.queryByRole("region", { name: "По минимальному взносу" }),
  ).toBeNull();
});
