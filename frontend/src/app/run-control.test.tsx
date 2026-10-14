// @vitest-environment jsdom
import {
  act,
  cleanup,
  renderHook,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { useJob } from "./useJob";
import Workspace from "./Workspace";
import sample from "../../../examples/senior-deposit.demo.json";
import type { Job } from "../types";
const running: Job = {
  id: "run-one",
  status: "running",
  done: 4,
  total: 30,
  record: null,
  error: null,
  saved: false,
};
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
it("discovers the active session run away from its page and again after workspace reload", async () => {
  vi.spyOn(api, "request").mockImplementation(
    <T,>() => Promise.resolve({ jobs: [running] }) as Promise<T>,
  );
  const first = renderHook(() => useJob("archive", () => {}));
  await act(async () => {});
  expect(first.result.current.active?.id).toBe("run-one");
  first.unmount();
  const refreshed = renderHook(() => useJob("methodology", () => {}));
  await act(async () => {});
  expect(refreshed.result.current.active?.done).toBe(4);
});
it("delivers a background completion once and clears the active run", async () => {
  vi.useFakeTimers();
  let finished = false;
  const deliveries: string[] = [];
  const completed: Job = {
    ...running,
    status: "completed",
    done: 30,
    saved: true,
  };
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string) =>
      Promise.resolve(
        path === "/runs" ? { jobs: finished ? [] : [running] } : completed,
      ) as Promise<T>,
  );
  const { result } = renderHook(() =>
    useJob("archive", (job) => deliveries.push(job.id)),
  );
  await act(async () => {});
  finished = true;
  await act(async () => vi.advanceTimersByTimeAsync(2000));
  expect(result.current.active).toBeNull();
  expect(deliveries).toEqual(["run-one"]);
  await act(async () => vi.advanceTimersByTimeAsync(4000));
  expect(deliveries).toEqual(["run-one"]);
});
it("a polling failure retains the last actual progress and retry recovers it", async () => {
  vi.useFakeTimers();
  let offline = false;
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string) =>
      (offline
        ? Promise.reject(new Error("connection unavailable"))
        : Promise.resolve(
            path === "/runs" ? { jobs: [running] } : running,
          )) as Promise<T>,
  );
  const { result } = renderHook(() => useJob("job/run-one", () => {}));
  await act(async () => {});
  offline = true;
  await act(async () => vi.advanceTimersByTimeAsync(2000));
  expect(result.current.job?.status).toBe("running");
  expect(result.current.job?.done).toBe(4);
  expect(result.current.error).toBe("connection unavailable");
  offline = false;
  await act(async () => result.current.refresh());
  expect(result.current.error).toBe("");
  expect(result.current.job?.status).toBe("running");
});
it("late responses after navigating or unmounting do not deliver an old run", async () => {
  let resolve!: (value: Job) => void;
  const late = new Promise<Job>((yes) => {
    resolve = yes;
  });
  const deliveries: string[] = [];
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string) =>
      (path === "/runs" ? Promise.resolve({ jobs: [] }) : late) as Promise<T>,
  );
  const { rerender, unmount } = renderHook(
    ({ route }) => useJob(route, (job) => deliveries.push(job.id)),
    { initialProps: { route: "job/run-one" } },
  );
  await act(async () => {});
  rerender({ route: "archive" });
  unmount();
  await act(async () => resolve({ ...running, status: "completed", done: 30 }));
  expect(deliveries).toEqual([]);
});
it("viewing a historical cancelled job still delivers another active run's completion", async () => {
  vi.useFakeTimers();
  let finished = false;
  const deliveries: string[] = [];
  const old: Job = { ...running, id: "old-run", status: "cancelled" };
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string) =>
      Promise.resolve(
        path === "/runs"
          ? { jobs: finished ? [] : [running] }
          : path === "/runs/old-run"
            ? old
            : { ...running, status: "completed", done: 30, saved: true },
      ) as Promise<T>,
  );
  const { result } = renderHook(() =>
    useJob("job/old-run", (job) => deliveries.push(job.id)),
  );
  await act(async () => {});
  finished = true;
  await act(async () => vi.advanceTimersByTimeAsync(2000));
  expect(result.current.job?.id).toBe("old-run");
  expect(result.current.active).toBeNull();
  expect(deliveries).toEqual(["old-run", "run-one"]);
});
it("a missing run after server restart clears the phantom active task", async () => {
  vi.useFakeTimers();
  let restarted = false;
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string) =>
      (path === "/runs"
        ? Promise.resolve({ jobs: restarted ? [] : [running] })
        : Promise.reject(new ApiError("run unavailable", 404))) as Promise<T>,
  );
  const { result } = renderHook(() => useJob("archive", () => {}));
  await act(async () => {});
  restarted = true;
  await act(async () => vi.advanceTimersByTimeAsync(2000));
  expect(result.current.active).toBeNull();
  expect(result.current.error).toContain("run unavailable");
  await act(async () => result.current.refresh());
  expect(result.current.active).toBeNull();
});
it("workspace retains a successful cancellation acknowledgement when the following poll fails", async () => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  window.location.hash = "/job/run-one";
  let stopped = false;
  vi.spyOn(api, "request").mockImplementation(<T,>(path: string) => {
    if (path === "/catalog")
      return Promise.resolve({
        scenarios: { student_card: sample.scenario },
        segments: {},
      }) as Promise<T>;
    if (path === "/experiments")
      return Promise.resolve({ records: [] }) as Promise<T>;
    if (path === "/recovery")
      return Promise.resolve({ jobs: [] }) as Promise<T>;
    if (path.endsWith("/cancel")) {
      stopped = true;
      return Promise.resolve({
        ...running,
        status: "cancelling",
      }) as Promise<T>;
    }
    return (
      stopped
        ? Promise.reject(new Error("connection unavailable"))
        : Promise.resolve(path === "/runs" ? { jobs: [running] } : running)
    ) as Promise<T>;
  });
  render(
    <Workspace
      session={{
        user: { id: "test", name: "Test", username: "test", role: "analyst" },
        csrf_token: "test",
        mode: "local",
        model: "demo",
      }}
      onLogout={() => {}}
    />,
  );
  await act(async () => {});
  await act(async () =>
    screen.getByRole("button", { name: "Остановить" }).click(),
  );
  expect(
    screen.getByRole("heading", {
      name: "Останавливаем исследование",
    }),
  ).toBeTruthy();
  expect(
    (
      screen.getByRole("button", {
        name: "Останавливаем…",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(
    screen.getByText("connection unavailable", { exact: false }),
  ).toBeTruthy();
});
