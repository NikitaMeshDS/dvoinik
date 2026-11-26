// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";
import Workspace from "./app/Workspace";
import JobView from "./JobView";
import { draftFromRun, runPayload } from "./draft";
import type { RunPayload, Job } from "./types";
import sample from "../../examples/senior-deposit.demo.json";
afterEach(() => {
  cleanup();
  sessionStorage.clear();
  vi.restoreAllMocks();
});
const request: RunPayload = {
  scenario_key: "senior_deposit",
  scenario: { ...sample.scenario, title: "Конфигурация неудачного запуска" },
  n: 100,
  seed: 73,
  mock: true,
  concurrency: 3,
};
it("restores exact scenario and run parameters without inventing a new origin", () => {
  const draft = draftFromRun(request, false);
  expect(runPayload(draft)).toEqual({ ...request, scenario_key: "custom" });
  draft.variants.A = "changed";
  expect(request.scenario.variants.A).not.toBe("changed");
});
it("failed runs no longer say they are executing and historical jobs do not promise restoration", () => {
  const props = {
    error: "",
    onRetry: vi.fn(),
    onCancel: vi.fn(),
    cancelBusy: false,
    onBack: vi.fn(),
    onBackground: vi.fn(),
  };
  render(
    <JobView
      {...props}
      job={{ id: "old", status: "failed", done: 0, total: 50 }}
    />,
  );
  expect(screen.queryByText(/запуск выполняется на сервере/)).toBeNull();
  expect(screen.getByRole("button", { name: "Открыть черновик" })).toBeTruthy();
});
it("recovers failed job settings after a fresh workspace load without starting a run", async () => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  window.location.hash = "/job/failed-run";
  const failed: Job = {
    id: "failed-run",
    status: "failed",
    done: 2,
    total: 300,
    error: "Provider unavailable",
    request,
  };
  const starts: unknown[] = [];
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string, method?: string, body?: unknown) => {
      if (path === "/catalog")
        return Promise.resolve({
          scenarios: { student_card: sample.scenario, custom: sample.scenario },
          segments: {},
        }) as Promise<T>;
      if (path === "/experiments")
        return Promise.resolve({ records: [] }) as Promise<T>;
      if (path === "/recovery" || (path === "/runs" && method !== "POST"))
        return Promise.resolve({ jobs: [] }) as Promise<T>;
      if (path === "/runs" && method === "POST") {
        starts.push(body);
        return Promise.reject(new Error("unexpected auto-start"));
      }
      return Promise.resolve(failed) as Promise<T>;
    },
  );
  render(
    <Workspace
      session={{
        user: {
          id: "recovery-user",
          name: "Test",
          username: "test",
          role: "analyst",
        },
        csrf_token: "x",
        mode: "local",
        model: "demo",
      }}
      onLogout={() => {}}
    />,
  );
  await act(async () => {});
  fireEvent.click(
    screen.getByRole("button", { name: "Восстановить настройки запуска" }),
  );
  expect(
    (
      await screen.findByRole("textbox", { name: "Название исследования" })
    ).getAttribute("value"),
  ).toBe(request.scenario.title);
  expect(starts).toHaveLength(0);
});

it("discovers interrupted runs from the archive and opens their settings", async () => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  window.location.hash = "/archive";
  const interrupted: Job = {
    id: "interrupted-run",
    status: "interrupted",
    done: 0,
    total: 300,
    request,
  };
  const starts: unknown[] = [];
  vi.spyOn(api, "request").mockImplementation(
    <T,>(path: string, method?: string, body?: unknown) => {
      if (path === "/catalog")
        return Promise.resolve({
          scenarios: { student_card: sample.scenario, custom: sample.scenario },
          segments: {},
        }) as Promise<T>;
      if (path === "/experiments")
        return Promise.resolve({ records: [] }) as Promise<T>;
      if (path === "/recovery")
        return Promise.resolve({ jobs: [interrupted] }) as Promise<T>;
      if (path === "/runs" && method === "POST") starts.push(body);
      if (path === "/runs") return Promise.resolve({ jobs: [] }) as Promise<T>;
      return Promise.resolve(interrupted) as Promise<T>;
    },
  );
  render(
    <Workspace
      session={{
        user: {
          id: "interrupted-owner",
          name: "Test",
          username: "test",
          role: "analyst",
        },
        csrf_token: "x",
        mode: "local",
        model: "demo",
      }}
      onLogout={() => {}}
    />,
  );
  fireEvent.click(
    await screen.findByRole("link", { name: request.scenario.title }),
  );
  expect(
    await screen.findByRole("heading", { name: "Исследование прервано" }),
  ).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Восстановить настройки запуска" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("textbox", { name: "Название исследования" }),
    ).toHaveProperty("value", request.scenario.title),
  );
  expect(starts).toHaveLength(0);
});
