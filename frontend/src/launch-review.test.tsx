// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
import Composer from "./Composer";
import { draftFromScenario } from "./draft";
import type { Catalog } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
const catalog: Catalog = {
  scenarios: { custom: sample.scenario },
  segments: {
    senior: {
      name: "Пенсионеры 60+",
      age: [60, 78],
      region: ["Тула"],
      income: [],
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
it("summarizes submitted offers and audience, updates after edits, and links back to offers", () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const d = draftFromScenario(sample.scenario, "custom", true);
  const page = (title: string, n: number) => (
    <Composer
      catalog={catalog}
      draft={{ ...d, title, n }}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      demo
      busy={false}
    />
  );
  const { rerender } = render(page("Тест запуска", 50));
  fireEvent.click(screen.getByRole("button", { name: "Далее: аудитория" }));
  const review = screen.getByRole("region", {
    name: "Проверьте перед запуском",
  });
  expect(review.textContent).toContain("Тест запуска");
  expect(review.textContent).toContain("50");
  expect(review.textContent).toContain(d.question);
  expect(review.textContent).toContain(d.variants.A);
  expect(review.textContent).toContain("Демо без внешних запросов");
  rerender(page("Новая версия", 100));
  expect(review.textContent).toContain("Новая версия");
  expect(review.textContent).not.toContain("Тест запуска");
  fireEvent.click(
    screen.getByRole("button", { name: "Изменить вопрос и предложения" }),
  );
  expect(
    screen.getByRole("textbox", { name: "Название исследования" }),
  ).toBeTruthy();
});
it("warns about equal normalized texts without treating absent hidden variants as offers", () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const d = draftFromScenario(sample.scenario, "custom", true);
  d.variantCount = 2;
  d.variants = {
    A: "Бесплатная  карта",
    B: " бесплатная\nкарта ",
    C: "Бесплатная карта",
  };
  render(
    <Composer
      catalog={catalog}
      draft={d}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      demo
      busy={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Далее: аудитория" }));
  expect(screen.getByText(/Совпадают тексты предложений: A, B/)).toBeTruthy();
  expect(
    screen.queryByText(/Совпадают тексты предложений: A, B, C/),
  ).toBeNull();
});

it("removes the previous estimate while new audience parameters are being calculated", async () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string, _method?: string, body?: unknown) => {
      const n = (body as { n: number }).n;
      return Promise.resolve(
        path === "/preview"
          ? { counts: { senior: n }, shares: { senior: 1 } }
          : {
              requests: n * 3 + 1,
              input_tokens: 1000,
              output_tokens: 200,
              minutes: 1,
              cost: null,
              currency: null,
              detail: "Расчёт для " + n,
            },
      ) as Promise<T>;
    },
  );
  const d = draftFromScenario(sample.scenario, "custom", false);
  const page = (n: number) => (
    <Composer
      catalog={catalog}
      draft={{ ...d, n }}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      demo={false}
      busy={false}
    />
  );
  const { rerender } = render(page(50));
  fireEvent.click(screen.getByRole("button", { name: "Далее: аудитория" }));
  await act(async () => vi.advanceTimersByTimeAsync(300));
  expect(screen.getByText(/Расчёт для 50/)).toBeTruthy();
  rerender(page(100));
  expect(screen.queryByText(/Расчёт для 50/)).toBeNull();
  await act(async () => vi.advanceTimersByTimeAsync(300));
  expect(screen.getByText(/Расчёт для 100/)).toBeTruthy();
  expect(screen.getByText(/Стоимость не рассчитана/)).toBeTruthy();
});
