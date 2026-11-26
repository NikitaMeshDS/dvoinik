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
  expect(runPayload(draft)).toEqual(request);
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
          scenarios: {
            student_card: sample.scenario,
            senior_deposit: sample.scenario,
            custom: sample.scenario,
          },
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

it.each([true, false])(
  "opens interrupted settings with original template available: %s",
  async (templateAvailable) => {
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
    const dismiss = vi.fn();
    const confirmation = vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.spyOn(api, "request").mockImplementation(
      <T,>(path: string, method?: string, body?: unknown) => {
        if (path === "/catalog")
          return Promise.resolve({
            scenarios: {
              student_card: sample.scenario,
              ...(templateAvailable ? { senior_deposit: sample.scenario } : {}),
              custom: sample.scenario,
            },
            segments: {},
          }) as Promise<T>;
        if (path === "/experiments")
          return Promise.resolve({ records: [] }) as Promise<T>;
        if (path === "/recovery")
          return Promise.resolve({ jobs: [interrupted] }) as Promise<T>;
        if (path === "/recovery/interrupted-run" && method === "DELETE")
          dismiss();
        if (path === "/preview")
          return Promise.resolve({ counts: {}, shares: {} }) as Promise<T>;
        if (path === "/runs" && method === "POST") {
          starts.push(body);
          return Promise.resolve({
            id: "new-run",
            status: "queued",
          }) as Promise<T>;
        }
        if (path === "/runs")
          return Promise.resolve({ jobs: [] }) as Promise<T>;
        return Promise.resolve(interrupted) as Promise<T>;
      },
    );
    const workspace = (
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
      />
    );
    const view = render(workspace);
    fireEvent.click(
      await screen.findByRole("button", {
        name: `Удалить настройки: ${request.scenario.title}`,
      }),
    );
    expect(confirmation).toHaveBeenCalled();
    expect(dismiss).not.toHaveBeenCalled();
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
    expect(screen.getByRole("combobox", { name: "Сценарий" })).toHaveProperty(
      "value",
      templateAvailable ? request.scenario_key : "custom",
    );
    expect(starts).toHaveLength(0);
    if (!templateAvailable) {
      view.unmount();
      render(workspace);
      expect(
        await screen.findByText(/восстановлены в вашем сценарии/),
      ).toBeTruthy();
      await screen.findByText(/Сохранено в этой вкладке/);
    }
    fireEvent.click(screen.getByRole("button", { name: "Далее: аудитория" }));
    const submit = await screen.findByRole<HTMLButtonElement>("button", {
      name: "Запустить исследование",
    });
    await waitFor(() => expect(submit.disabled).toBe(false));
    fireEvent.click(submit);
    expect(starts).toEqual([
      {
        ...request,
        scenario_key: templateAvailable ? request.scenario_key : "custom",
      },
    ]);
  },
);
