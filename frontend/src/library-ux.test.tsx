// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import Library, { INITIAL_LIBRARY } from "./Library";
import type { Experiment } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
const makeRecord = (id: string, mock = true): Experiment => ({
  ...sample,
  id,
  mock,
  scenario: {
    ...sample.scenario,
    title: mock ? "Вклад для пенсионеров" : "Карта для студентов",
  },
  report: Object.fromEntries(
    Object.entries(sample.report).map(([key, value]) => [
      key,
      {
        ...value,
        confidence_interval: [
          value.confidence_interval[0],
          value.confidence_interval[1],
        ] as [number, number],
      },
    ]),
  ),
});
function Catalogue({
  records = [makeRecord("demo"), makeRecord("llm", false)],
}: {
  records?: Experiment[];
}) {
  const [state, onState] = useState(INITIAL_LIBRARY);
  return (
    <Library
      records={records}
      state={state}
      onState={onState}
      onNew={() => {}}
      onOpen={() => {}}
      onImport={() => {}}
      onSample={() => {}}
      onCompare={() => {}}
      pending={new Set()}
    />
  );
}
afterEach(cleanup);
it("reveals advanced filters on demand and keeps an applied filter visible when collapsed", () => {
  render(<Catalogue />);
  expect(
    screen.queryByRole("combobox", { name: "Режим исследований" }),
  ).toBeNull();
  const filters = screen.getByRole("button", { name: "Фильтры" });
  expect(
    document.getElementById(filters.getAttribute("aria-controls")!)?.hidden,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
  expect(
    screen
      .getByRole("button", { name: "Фильтры" })
      .getAttribute("aria-expanded"),
  ).toBe("true");
  fireEvent.change(
    screen.getByRole("combobox", { name: "Режим исследований" }),
    { target: { value: "llm" } },
  );
  expect(screen.queryByText("Вклад для пенсионеров")).toBeNull();
  expect(screen.getByText("Карта для студентов")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Фильтры, активно: 1" }));
  expect(
    screen.queryByRole("combobox", { name: "Режим исследований" }),
  ).toBeNull();
  expect(
    screen
      .getByRole("button", { name: "Фильтры, активно: 1" })
      .getAttribute("aria-expanded"),
  ).toBe("false");
  fireEvent.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
  expect(screen.getByText("Вклад для пенсионеров")).toBeTruthy();
});
it("the no-results action resets search and filters instead of leaving the researcher stuck", () => {
  render(<Catalogue />);
  fireEvent.change(
    screen.getByRole("textbox", { name: "Поиск исследований" }),
    { target: { value: "неизвестная гипотеза" } },
  );
  expect(screen.getByRole("heading", { name: "Совпадений нет" })).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Сбросить поиск и фильтры" }),
  );
  expect(
    (
      screen.getByRole("textbox", {
        name: "Поиск исследований",
      }) as HTMLInputElement
    ).value,
  ).toBe("");
  expect(screen.getByText("Вклад для пенсионеров")).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "Следующая страница" }),
  ).toBeNull();
});
it("filters applied from a later page return to the first result and hide unnecessary paging", () => {
  render(
    <Catalogue
      records={Array.from({ length: 9 }, (_, i) =>
        makeRecord(String(i), i !== 8),
      )}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Следующая страница" }));
  fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
  fireEvent.change(
    screen.getByRole("combobox", { name: "Режим исследований" }),
    { target: { value: "llm" } },
  );
  expect(screen.getByText("Карта для студентов")).toBeTruthy();
  expect(
    screen.queryByRole("button", { name: "Следующая страница" }),
  ).toBeNull();
});
it("clearing search and filters restores keyboard focus to a persistent control", () => {
  render(<Catalogue />);
  const search = screen.getByRole("textbox", { name: "Поиск исследований" });
  fireEvent.change(search, { target: { value: "Вклад" } });
  const clear = screen.getByRole("button", { name: "Очистить поиск" });
  clear.focus();
  fireEvent.click(clear);
  expect(document.activeElement).toBe(search);
  fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
  fireEvent.change(
    screen.getByRole("combobox", { name: "Режим исследований" }),
    { target: { value: "llm" } },
  );
  const reset = screen.getByRole("button", { name: "Сбросить фильтры" });
  reset.focus();
  fireEvent.click(reset);
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "Фильтры" }),
  );
});
it("resetting an empty result returns keyboard focus to search", () => {
  render(<Catalogue />);
  const search = screen.getByRole("textbox", { name: "Поиск исследований" });
  fireEvent.change(search, { target: { value: "неизвестная гипотеза" } });
  const reset = screen.getByRole("button", {
    name: "Сбросить поиск и фильтры",
  });
  reset.focus();
  fireEvent.click(reset);
  expect(document.activeElement).toBe(search);
});
