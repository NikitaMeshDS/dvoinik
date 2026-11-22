// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Composer from "./Composer";
import { draftFromScenario } from "./draft";
import { api } from "./api";
import type { Catalog, Draft } from "./types";
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
    student_msk: {
      name: "Студенты",
      age: [18, 22],
      region: ["Москва"],
      income: [],
      habits: [],
      attitude: [],
    },
  },
};
const draft = () => ({
  ...draftFromScenario(sample.scenario, "custom", true),
  variantCount: 2,
  weights: { senior: 1, student_msk: 3 },
});
function page(d: Draft, step = 0) {
  return (
    <Composer
      catalog={catalog}
      draft={d}
      step={step}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      demo
      busy={false}
    />
  );
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it("previews one participant form at a time and follows edits to the selected offer", () => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const d = draft();
  const { rerender } = render(page(d));
  fireEvent.click(screen.getByText("Как выглядит вопрос для участника"));
  const preview = screen.getByRole("region", { name: "Предпросмотр вопроса" });
  expect(preview.textContent).toContain(d.question);
  expect(preview.textContent).toContain(d.variants.A);
  expect(preview.textContent).not.toContain(d.variants.B);
  expect(preview.textContent).not.toContain(d.variants.C);
  expect(
    within(preview).queryByRole("button", { name: "Вариант C" }),
  ).toBeNull();
  const second = within(preview).getByRole("button", { name: "Вариант B" });
  fireEvent.click(second);
  expect(second.getAttribute("aria-pressed")).toBe("true");
  expect(preview.textContent).toContain(d.variants.B);
  expect(preview.textContent).not.toContain(d.variants.A);
  expect(within(preview).queryByRole("checkbox")).toBeNull();
  rerender(
    page({
      ...d,
      question: "Новый вопрос?",
      variants: { ...d.variants, B: "Новый вариант B" },
    }),
  );
  expect(preview.textContent).toContain("Новый вопрос?");
  expect(preview.textContent).toContain("Новый вариант B");
  expect(preview.textContent).not.toContain(d.variants.B);
});
it("shows normalized audience shares from current preview and hides them immediately after edits", async () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string) =>
      Promise.resolve(
        path === "/preview"
          ? {
              shares: { senior: 0.25, student_msk: 0.75 },
              counts: { senior: 13, student_msk: 37 },
            }
          : {
              requests: 101,
              input_tokens: 100,
              output_tokens: 100,
              minutes: 1,
              cost: null,
              currency: null,
              detail: "",
            },
      ) as Promise<T>,
  );
  const d = { ...draft(), n: 50 };
  const { rerender } = render(page(d, 1));
  const distribution = screen.getByRole("region", {
    name: "Состав синтетической аудитории",
  });
  expect(distribution.textContent).not.toContain("25,0%");
  await act(async () => vi.advanceTimersByTimeAsync(300));
  expect(distribution.textContent).toContain("25,0%");
  expect(distribution.textContent).toContain("75,0%");
  expect(distribution.textContent).toContain("13 профилей");
  rerender(page({ ...d, weights: { senior: 3, student_msk: 1 } }, 1));
  expect(distribution.textContent).not.toContain("25,0%");
  expect(distribution.textContent).not.toContain("75,0%");
});
it("does not keep the audience visualization busy after preview failure", async () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  vi.spyOn(api, "request").mockRejectedValue(new Error("Preview unavailable"));
  render(page(draft(), 1));
  await act(async () => vi.advanceTimersByTimeAsync(300));
  const distribution = screen.getByRole("region", {
    name: "Состав синтетической аудитории",
  });
  expect(distribution.getAttribute("aria-busy")).toBe("false");
  expect(within(distribution).queryByRole("status")).toBeNull();
});

it("waits for an explicit audience choice before requesting a preview", async () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const request = vi
    .spyOn(api, "request")
    .mockRejectedValue(new Error("offline"));
  const d = draft();
  const { rerender } = render(page({ ...d, weights: {} }, 1));
  await act(async () => vi.advanceTimersByTimeAsync(300));
  expect(request).not.toHaveBeenCalled();
  rerender(page(d, 1));
  await act(async () => vi.advanceTimersByTimeAsync(300));
  expect(request.mock.calls.some(([path]) => path === "/preview")).toBe(true);
});
