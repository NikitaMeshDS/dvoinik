// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import LikertBars from "./features/reports/LikertBars";
import Methodology from "./Methodology";
import sample from "../../examples/senior-deposit.demo.json";
import type { Catalog, Experiment } from "./types";
const record = sample as unknown as Experiment;
afterEach(cleanup);
it("draws the 1–5 distribution only for SSR studies", () => {
  const { container, rerender } = render(<LikertBars report={record.report} />);
  expect(container.innerHTML).toBe("");
  rerender(
    <LikertBars
      report={{
        ...record.report,
        C: { ...record.report.C, likert: [0.1, 0.1, 0.2, 0.3, 0.3] },
      }}
    />,
  );
  expect(screen.getByText("Ответы по шкале 1–5")).toBeTruthy();
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain(
    "Точно да 30,0%",
  );
});
it("names low-income segments as a distortion risk in the methodology", () => {
  const catalog: Catalog = {
    scenarios: {},
    segments: {
      senior: {
        name: "Пенсионеры 60+",
        age: [60, 78],
        region: [],
        income: [],
        habits: [],
        attitude: [],
      },
    },
    sources: { segments: {}, gaps: "" },
    risks: {
      segments: { senior: "Низкий доход" },
      source: "https://example.org",
    },
  };
  render(<Methodology catalog={catalog} />);
  expect(
    screen.getByText(/Сегменты с низким доходом — Пенсионеры 60\+/),
  ).toBeTruthy();
  expect(screen.getByText(/Режим SSR/)).toBeTruthy();
});
