// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import Methodology from "./Methodology";
import type { Catalog } from "./types";
afterEach(cleanup);
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
  sources: {
    segments: {
      senior: [
        {
          fact: "Средний размер пенсии — 25 399 ₽",
          use: "Диапазон дохода включает среднее.",
          status: "согласуется",
          source: "Социальный фонд России",
          date: "июнь 2026",
          url: "https://example.org/pension",
        },
      ],
    },
    gaps: "Для молодых семей опорных цифр пока нет.",
  },
};
it("lists segment sources with status, link and remaining gaps", () => {
  render(<Methodology catalog={catalog} />);
  expect(screen.getByText("С чем сверены сегменты")).toBeTruthy();
  expect(screen.getByText("Пенсионеры 60+")).toBeTruthy();
  expect(screen.getByText("Согласуется")).toBeTruthy();
  const link = screen.getByRole("link", {
    name: "Социальный фонд России, июнь 2026",
  });
  expect(link.getAttribute("href")).toBe("https://example.org/pension");
  expect(
    screen.getByText("Для молодых семей опорных цифр пока нет."),
  ).toBeTruthy();
});
it("renders without catalog sources", () => {
  render(<Methodology />);
  expect(screen.queryByText("С чем сверены сегменты")).toBeNull();
});

it("shows measured results with limits", () => {
  render(<Methodology />);
  expect(screen.getByText("Что показали замеры")).toBeTruthy();
  expect(screen.getByText("qwen3-30b-a3b, SSR")).toBeTruthy();
  expect(screen.getByText(/Доли рынка двойники не прогнозируют/)).toBeTruthy();
});
