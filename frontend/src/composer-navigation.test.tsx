// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
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
it("shows a minimum deposit in each copy of the same draft", () => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const draft = draftFromScenario(sample.scenario, "custom");
  const resolve = vi.fn();
  render(
    <Composer
      catalog={catalog}
      draft={draft}
      onChange={vi.fn()}
      onTemplate={vi.fn()}
      onRun={vi.fn()}
      demo
      busy={false}
      backups={[
        { ...draft, depositMinimumRub: 10000 },
        { ...draft, depositMinimumRub: 50000 },
        { ...draft, depositMinimumRub: undefined },
      ]}
      onResolveBackup={resolve}
    />,
  );
  const details = screen.getByText(/^Копия 2/).closest("details")!;
  fireEvent.click(within(details).getByText(/^Копия 2/));
  expect(within(details).getByText(/Минимальный взнос/).textContent).toMatch(
    /50\s000\s₽/,
  );
  expect(screen.getByText(/Минимальный взнос не задан/)).toBeTruthy();
  fireEvent.click(
    within(details).getByRole("button", { name: "Восстановить копию" }),
  );
  expect(resolve).toHaveBeenCalledWith(true, 1);
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

it.each([
  ["title", "Название исследования"],
  ["question", "Вопрос двойникам"],
  ["offer", "Предложение B"],
  ["objections", "Категории отказа — одна на строку"],
])("focuses and describes the invalid %s field", (field, label) => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const draft = draftFromScenario(sample.scenario, "custom", true);
  if (field === "title") draft.title = "";
  if (field === "question") draft.question = "";
  if (field === "offer") draft.variants.B = "";
  if (field === "objections") draft.objections = [];
  const run = vi.fn();
  render(
    <Composer
      catalog={catalog}
      draft={draft}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={run}
      demo
      busy={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Далее: аудитория" }));
  const input = screen.getByRole("textbox", { name: label });
  expect(document.activeElement).toBe(input);
  expect(input.getAttribute("aria-invalid")).toBe("true");
  expect(
    document.getElementById(input.getAttribute("aria-describedby")!)
      ?.textContent,
  ).toBeTruthy();
  if (field === "objections") expect(input.closest("details")?.open).toBe(true);
  expect(run).not.toHaveBeenCalled();
  expect(
    (
      screen.getByRole("textbox", {
        name: "Предложение A",
      }) as HTMLTextAreaElement
    ).value,
  ).toBe(draft.variants.A);
});

it("focuses audience selection when all weights are zero", () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const draft = draftFromScenario(sample.scenario, "custom", true);
  draft.weights = { senior: 0 };
  render(
    <Composer
      catalog={catalog}
      draft={draft}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      demo
      busy={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Далее: аудитория" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Запустить исследование" }),
  );
  const input = screen.getByRole("spinbutton", { name: "Доля: Пенсионеры" });
  expect(document.activeElement).toBe(input);
  expect(input.getAttribute("aria-invalid")).toBe("true");
});

it("reveals invalid advanced settings on the audience stage", () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const draft = draftFromScenario(sample.scenario, "custom", true);
  draft.seed = -1;
  render(
    <Composer
      catalog={catalog}
      draft={draft}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      demo
      busy={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Далее: аудитория" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Запустить исследование" }),
  );
  const input = screen.getByRole("spinbutton", {
    name: "Seed популяции и демо",
  });
  expect(document.activeElement).toBe(input);
  expect(input.closest("details")?.open).toBe(true);
});

it("clears an obsolete field error after resetting the draft", () => {
  vi.useFakeTimers();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  const draft = draftFromScenario(sample.scenario, "custom", true);
  const view = (title: string) => (
    <Composer
      catalog={catalog}
      draft={{ ...draft, title }}
      onChange={() => {}}
      onTemplate={() => {}}
      onRun={() => {}}
      onReset={() => rerender(view(draft.title))}
      demo
      busy={false}
    />
  );
  const { rerender } = render(view(""));
  fireEvent.click(screen.getByRole("button", { name: "Далее: аудитория" }));
  fireEvent.click(screen.getByRole("button", { name: "Начать заново" }));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(
    screen
      .getByRole("textbox", { name: "Название исследования" })
      .getAttribute("aria-invalid"),
  ).toBeNull();
});
