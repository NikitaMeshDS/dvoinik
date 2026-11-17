// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { ComparisonDialog } from "./Compare";
import type { Comparison, Experiment } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.removeAttribute("open");
    },
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it("shows concrete comparison limits before deltas and offers actual text mapping", async () => {
  const left = { ...sample, id: "left" } as unknown as Experiment;
  const right = {
    ...left,
    id: "right",
    scenario: {
      ...left.scenario,
      variants: { ...left.scenario.variants, A: "Другой текст A" },
    },
  };
  const response: Comparison = {
    left,
    right,
    comparison: {
      changes: [],
      warnings: [
        { code: "population", text: "Аудитория различается." },
        { code: "variant_text", text: "Тексты изменены." },
      ],
      variants: [
        {
          variant: "A",
          left: 0.4,
          right: 0.5,
          left_n: 50,
          right_n: 50,
          delta_pp: 10,
        },
      ],
      segments: [],
    },
  };
  vi.spyOn(api, "request").mockImplementation(
    <T,>() => Promise.resolve(response) as Promise<T>,
  );
  render(
    <ComparisonDialog
      ids={["left", "right"]}
      records={[left, right]}
      onClose={() => {}}
      onError={() => {}}
    />,
  );
  await act(async () => {});
  expect(screen.getByRole("combobox", { name: "Запуск 1" })).toBeTruthy();
  expect(screen.getByRole("combobox", { name: "Запуск 2" })).toBeTruthy();
  const warning = screen.getByRole("region", { name: "Ограничения сравнения" });
  expect(warning.textContent).toContain("Аудитория различается.");
  const table = screen.getAllByRole("table")[0];
  expect(
    warning.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(screen.getByText("Другой текст A")).toBeTruthy();
  expect(screen.getByText(/Дельта = запуск 2 минус запуск 1/)).toBeTruthy();
});
it("keeps old comparison responses readable without claiming unchanged conditions prove an effect", async () => {
  const left = { ...sample, id: "left" } as unknown as Experiment;
  vi.spyOn(api, "request").mockImplementation(
    <T,>() =>
      Promise.resolve({
        left,
        right: { ...left, id: "right" },
        comparison: { changes: [], variants: [], segments: [] },
      }) as Promise<T>,
  );
  render(
    <ComparisonDialog
      ids={["left", "right"]}
      records={[left, { ...left, id: "right" }]}
      onClose={() => {}}
      onError={() => {}}
    />,
  );
  await act(async () => {});
  expect(screen.getByText(/не доказывают причинный эффект/)).toBeTruthy();
  expect(
    screen.queryByRole("region", { name: "Ограничения сравнения" }),
  ).toBeNull();
});
