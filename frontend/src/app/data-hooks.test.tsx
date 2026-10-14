// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { useArchive } from "./useArchive";
import { useRecord } from "./useRecord";
import sample from "../../../examples/senior-deposit.demo.json";
import type { Experiment } from "../types";
const record = (id: string): Experiment => ({
  ...sample,
  id,
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
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
it("saving before the initial archive read finishes reloads the complete list instead of hiding existing records", async () => {
  const old = deferred<{ records: Experiment[] }>(),
    fresh = deferred<{ records: Experiment[] }>();
  let reads = 0;
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string) =>
      (path === "/recovery"
        ? Promise.resolve({ jobs: [] })
        : ++reads === 1
          ? old.promise
          : fresh.promise) as Promise<T>,
  );
  const { result } = renderHook(() => useArchive());
  await act(async () => {});
  await act(async () => {
    result.current.updated(record("new"));
  });
  await act(async () => {
    old.resolve({ records: [record("one"), record("two")] });
    fresh.resolve({ records: [record("one"), record("two"), record("new")] });
  });
  expect(result.current.records.map((r) => r.id)).toEqual([
    "one",
    "two",
    "new",
  ]);
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBe("");
});
it("a late save for A cannot cancel B's read or show A under B's route", async () => {
  const first = deferred<Experiment>(),
    second = deferred<Experiment>();
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string) =>
      (path.endsWith("/A") ? first.promise : second.promise) as Promise<T>,
  );
  const { result, rerender } = renderHook(({ route }) => useRecord(route), {
    initialProps: { route: "report/A" },
  });
  await act(async () => first.resolve(record("A")));
  const saveFromA = result.current.updated;
  rerender({ route: "report/B" });
  await act(async () => saveFromA(record("A")));
  await act(async () => second.resolve(record("B")));
  expect(result.current.record?.id).toBe("B");
});
it("a save arriving between read completion and its UI commit remains visible", async () => {
  const old = deferred<Experiment>(),
    retry = deferred<Experiment>();
  let reads = 0;
  vi.spyOn(api, "request").mockImplementation(
    <T,>() => (++reads === 1 ? old.promise : retry.promise) as Promise<T>,
  );
  const { result } = renderHook(() => useRecord("report/A"));
  await act(async () => old.resolve(record("A")));
  const saved = {
    ...record("A"),
    validation: {
      created_at: "2026-10-14T00:00:00Z",
      cells: [],
      result: {
        mae_conversion: 0,
        spearman_variants: null,
        winner_match: null,
        survey_n: 0,
        matched_cells: 0,
        cells: [],
        actual_winners: [],
        predicted_winners: [],
      },
    },
  };
  const save = result.current.updated;
  await act(async () => result.current.retry());
  await act(async () => {
    retry.resolve(record("A"));
    await Promise.resolve();
    save(saved);
  });
  expect(result.current.record).toBe(saved);
});
it("a failed refresh retains the readable archive and a successful retry clears the error", async () => {
  let reads = 0;
  vi.spyOn(api, "request").mockImplementation(<T,>(path: string) => {
    if (path === "/recovery")
      return Promise.resolve({ jobs: [] }) as Promise<T>;
    reads++;
    return (
      reads === 2
        ? Promise.reject(new Error("archive unavailable"))
        : Promise.resolve({
            records:
              reads === 1 ? [record("one")] : [record("one"), record("two")],
          })
    ) as Promise<T>;
  });
  const { result } = renderHook(() => useArchive());
  await act(async () => {});
  await act(async () => result.current.reload());
  expect(result.current.records.map((r) => r.id)).toEqual(["one"]);
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBe("archive unavailable");
  await act(async () => result.current.reload());
  expect(result.current.records.map((r) => r.id)).toEqual(["one", "two"]);
  expect(result.current.error).toBe("");
});
