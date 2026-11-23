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

it("shows the profile for the current seed and explains demo use", async () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const request = vi
    .spyOn(api, "request")
    .mockImplementation(
      <T,>(path: string, _method?: string, body?: unknown) => {
        if (path !== "/preview") return Promise.reject(new Error());
        const { seed } = body as { seed: number };
        return Promise.resolve({
          counts: { senior: 50 },
          shares: { senior: 1 },
          respondent_system: "Отвечай от лица клиента.",
          profiles: {
            senior: {
              id: 0,
              text: `Анкета ${seed}`,
              available_deposit_rub: 50000,
              offer_prompts: { A: `Вклад A · ${seed}`, B: `Вклад B · ${seed}` },
            },
          },
        }) as Promise<T>;
      },
    );
  const d = draftFromScenario(sample.scenario, "senior_deposit", true);
  const page = (seed: number) => (
    <Composer
      catalog={catalog}
      draft={{ ...d, n: 50, seed, depositMinimumRub: 50000 }}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      demo
      busy={false}
      step={1}
    />
  );
  const { rerender } = render(page(42));
  fireEvent.click(screen.getByText("Что увидит двойник"));
  await act(async () => vi.advanceTimersByTimeAsync(200));
  expect(screen.getByText("Анкета 42")).toBeTruthy();
  expect(screen.getByText(/запросы к модели не отправляются/)).toBeTruthy();
  expect(
    screen.getByText(/Синтетическая сумма для проверки взноса/),
  ).toBeTruthy();
  fireEvent.click(screen.getByText("Текст запроса к модели"));
  expect(screen.getByText("Вклад A · 42")).toBeTruthy();
  fireEvent.change(
    screen.getByRole("combobox", { name: "Предложение в запросе" }),
    {
      target: { value: "B" },
    },
  );
  expect(screen.getByText("Вклад B · 42")).toBeTruthy();
  expect(screen.queryByText("Вклад A · 42")).toBeNull();
  fireEvent.click(screen.getByText("Инструкция модели"));
  expect(screen.getByText("Отвечай от лица клиента.")).toBeTruthy();
  expect(request).toHaveBeenCalledWith(
    "/preview",
    "POST",
    expect.objectContaining({
      seed: 42,
      scenario_key: "senior_deposit",
      deposit: true,
    }),
    expect.any(AbortSignal),
  );
  rerender(page(43));
  expect(screen.queryByText("Анкета 42")).toBeNull();
  await act(async () => vi.advanceTimersByTimeAsync(200));
  expect(screen.getByText("Анкета 43")).toBeTruthy();
});
