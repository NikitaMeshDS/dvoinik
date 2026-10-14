// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Composer from "./Composer";
import { draftFromScenario } from "./draft";
import type { Catalog } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
const catalog: Catalog = {
  scenarios: { custom: sample.scenario },
  segments: {
    senior: {
      name: "Пенсионеры",
      age: [60, 78],
      region: ["Тула"],
      income: ["пенсия"],
      habits: [],
      attitude: [],
    },
  },
};
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it("changing wizard steps focuses the new stage while editing its parameters preserves field focus", () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const draft = draftFromScenario(sample.scenario, "custom", true);
  const page = (n: number) => (
    <Composer
      catalog={catalog}
      draft={{ ...draft, n }}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      demo
      busy={false}
    />
  );
  const { rerender } = render(page(200));
  const next = screen.getByRole("button", { name: "Далее: аудитория" });
  next.focus();
  fireEvent.click(next);
  expect(document.activeElement).toBe(
    screen.getByRole("region", { name: "Аудитория исследования" }),
  );
  const size = screen.getByRole("combobox", { name: "Размер аудитории" });
  size.focus();
  rerender(page(100));
  expect(document.activeElement).toBe(size);
});
