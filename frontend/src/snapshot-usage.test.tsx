// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import SnapshotDetails from "./features/reports/SnapshotDetails";
import sample from "../../examples/senior-deposit.demo.json";
import type { Experiment } from "./types";

it("distinguishes historical, missing and partially reported usage", () => {
  const record = { ...(sample as unknown as Experiment), mock: false };
  const view = render(<SnapshotDetails record={record} />);
  expect(
    screen.getByText(/Учёт обращений к модели в этом снимке отсутствует/),
  ).toBeTruthy();
  const usage = {
    concurrency: 2,
    sdk_calls: 3,
    calls_with_usage: 0,
    reported_tokens: null,
    cache_hits: 1,
  };
  view.rerender(<SnapshotDetails record={{ ...record, run_usage: usage }} />);
  expect(screen.getByText(/Данные о расходе токенов отсутствуют/)).toBeTruthy();
  view.rerender(
    <SnapshotDetails
      record={{
        ...record,
        run_usage: { ...usage, calls_with_usage: 1, reported_tokens: 14 },
      }}
    />,
  );
  expect(screen.getByText(/14 токенов по 1 из 3 вызовов/)).toBeTruthy();
});
