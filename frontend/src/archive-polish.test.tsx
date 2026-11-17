// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Library, { INITIAL_LIBRARY } from "./Library";
import type { Experiment } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
const parent = {
  ...sample,
  id: "parent",
  scenario: { ...sample.scenario, title: "Исходный вклад" },
} as unknown as Experiment;
const child: Experiment = {
  ...parent,
  id: "child",
  scenario: {
    ...parent.scenario,
    title: "Итерация вклада",
    origin: { kind: "iteration", record_id: "parent", title: "Исходный вклад" },
  },
};
function show(records: Experiment[]) {
  const onOpen = vi.fn();
  render(
    <Library
      records={records}
      state={INITIAL_LIBRARY}
      onState={() => {}}
      onNew={() => {}}
      onOpen={onOpen}
      onImport={() => {}}
      onSample={() => {}}
      onCompare={() => {}}
      pending={new Set()}
    />,
  );
  return onOpen;
}
afterEach(cleanup);
it("opens a child's source separately from its report and shows real related run count", () => {
  const open = show([parent, child]);
  const source = screen.getByRole("button", {
    name: "Исходное исследование — Исходный вклад",
  });
  expect(source.parentElement?.closest("button")).toBeNull();
  fireEvent.click(source);
  expect(open).toHaveBeenLastCalledWith("parent");
  expect(screen.getByText("1 связанный запуск")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /^Итерация вклада/ }));
  expect(open).toHaveBeenLastCalledWith("child");
});
it("keeps the child accessible when its source is absent without offering a broken source action", () => {
  show([child]);
  expect(
    screen.queryByRole("button", { name: /Исходное исследование —/ }),
  ).toBeNull();
  expect(screen.getByText(/Источник недоступен в архиве/)).toBeTruthy();
  expect(screen.getByRole("button", { name: /^Итерация вклада/ })).toBeTruthy();
});
