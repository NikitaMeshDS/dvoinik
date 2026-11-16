// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ValidationPanel from "./features/reports/ValidationPanel";
import type { Experiment } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
import { api } from "./api";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it("sends the declared source unchanged to preview and save, locking it while preview exists", async () => {
  const record = structuredClone(sample) as unknown as Experiment;
  const protocol = {
    recruitment: "Опрос в университете",
    assignment: "random_one",
  };
  const saved = {
    ...record,
    validation: {
      created_at: "2026-11-16",
      protocol,
      cells: [],
      result: {
        survey_n: 2,
        matched_cells: 1,
        cells: [],
        mae_conversion: 0,
        spearman_variants: null,
        winner_match: null,
        actual_winners: [],
        predicted_winners: [],
      },
    },
  };
  const calls: unknown[] = [];
  vi.spyOn(api, "request").mockImplementation(
    <T,>(_path: string, method?: string, body?: unknown) => {
      calls.push(body);
      return Promise.resolve(
        method === "PUT"
          ? saved
          : { record: saved, base_validation: null, preview_id: "p" },
      ) as Promise<T>;
    },
  );
  const updated = vi.fn();
  render(
    <ValidationPanel
      record={record}
      catalog={{ scenarios: {}, segments: {} }}
      onUpdated={updated}
      onExport={() => {}}
    />,
  );
  fireEvent.click(screen.getByText("Как собраны ответы"));
  fireEvent.change(screen.getByLabelText("Способ набора участников"), {
    target: { value: protocol.recruitment },
  });
  fireEvent.change(screen.getByLabelText("Распределение предложений"), {
    target: { value: protocol.assignment },
  });
  const file = new File(["csv"], "answers.csv");
  Object.defineProperty(file, "text", { value: () => Promise.resolve("csv") });
  await act(async () =>
    fireEvent.change(screen.getByLabelText("CSV живого опроса"), {
      target: { files: [file] },
    }),
  );
  expect(calls[0]).toEqual({ csv: "csv", protocol });
  expect(
    (screen.getByLabelText("Способ набора участников") as HTMLInputElement)
      .disabled,
  ).toBe(true);
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Сохранить проверку" })),
  );
  expect(calls[1]).toEqual({ csv: "csv", protocol, base_validation: null });
  expect(updated).toHaveBeenCalledWith(saved);
});
it("describes unknown provenance in historical survey snapshots", () => {
  const record = {
    ...sample,
    validation: {
      created_at: "2026-11-16",
      cells: [],
      result: {
        survey_n: 2,
        matched_cells: 1,
        cells: [],
        mae_conversion: 0,
        spearman_variants: null,
        winner_match: null,
        actual_winners: [],
        predicted_winners: [],
      },
    },
  } as unknown as Experiment;
  render(
    <ValidationPanel
      record={record}
      catalog={{ scenarios: {}, segments: {} }}
      onUpdated={() => {}}
      onExport={() => {}}
    />,
  );
  expect(
    screen.getByText(/Сведения о сборе ответов не сохранены/),
  ).toBeTruthy();
});

it("keeps source details editable when discarding only the CSV preview", async () => {
  const record = structuredClone(sample) as unknown as Experiment;
  const saved = {
    ...record,
    validation: {
      created_at: "2026-11-16",
      cells: [],
      result: {
        survey_n: 2,
        matched_cells: 1,
        cells: [],
        mae_conversion: 0,
        spearman_variants: null,
        winner_match: null,
        actual_winners: [],
        predicted_winners: [],
      },
    },
  };
  vi.spyOn(api, "request").mockImplementation(
    <T,>() =>
      Promise.resolve({
        record: saved,
        base_validation: null,
        preview_id: "p",
      }) as Promise<T>,
  );
  render(
    <ValidationPanel
      record={record}
      catalog={{ scenarios: {}, segments: {} }}
      onUpdated={() => {}}
      onExport={() => {}}
    />,
  );
  fireEvent.click(screen.getByText("Как собраны ответы"));
  fireEvent.change(screen.getByLabelText("Способ набора участников"), {
    target: { value: "Пилот университета" },
  });
  const file = new File(["csv"], "answers.csv");
  Object.defineProperty(file, "text", { value: () => Promise.resolve("csv") });
  await act(async () =>
    fireEvent.change(screen.getByLabelText("CSV живого опроса"), {
      target: { files: [file] },
    }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Отменить предпросмотр" }),
  );
  const source = screen.getByLabelText(
    "Способ набора участников",
  ) as HTMLInputElement;
  expect(source.value).toBe("Пилот университета");
  expect(source.disabled).toBe(false);
});
