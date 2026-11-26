// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useDrafts } from "./useDrafts";
import { api } from "../api";
import { useSession } from "./useSession";
import { draftFromScenario } from "../draft";
import type { Catalog, Session } from "../types";
import sample from "../../../examples/senior-deposit.demo.json";
const catalog: Catalog = {
  scenarios: { student_card: sample.scenario, custom: sample.scenario },
  segments: {
    senior: {
      name: "Пенсионеры",
      age: [60, 78],
      region: [],
      income: [],
      habits: [],
      attitude: [],
    },
  },
};
const session = (id = "alice"): Session => ({
  user: { id, username: id, name: id, role: "analyst" },
  csrf_token: id,
  mode: "local",
  model: "test",
});
beforeEach(() => sessionStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
it("restores edited template, invalid unfinished text and stage after remount", () => {
  const first = renderHook(() => useDrafts(catalog, session()));
  act(() => first.result.current.choose("custom"));
  act(() =>
    first.result.current.update({
      ...first.result.current.draft!,
      title: "Рабочий черновик",
      question: "",
    }),
  );
  act(() => first.result.current.setStep(1));
  first.unmount();
  const restored = renderHook(() => useDrafts(catalog, session()));
  expect(restored.result.current.draft?.key).toBe("custom");
  expect(restored.result.current.draft?.title).toBe("Рабочий черновик");
  expect(restored.result.current.draft?.question).toBe("");
  expect(restored.result.current.step).toBe(1);
  expect(restored.result.current.status).toContain("Сохранено");
});
it("does not leak or overwrite drafts on owner changes", () => {
  const hook = renderHook(({ owner }) => useDrafts(catalog, session(owner)), {
    initialProps: { owner: "alice" },
  });
  act(() =>
    hook.result.current.update({
      ...hook.result.current.draft!,
      title: "Alice private",
    }),
  );
  hook.rerender({ owner: "bob" });
  expect(hook.result.current.draft?.title).not.toBe("Alice private");
  act(() =>
    hook.result.current.update({
      ...hook.result.current.draft!,
      title: "Bob private",
    }),
  );
  hook.rerender({ owner: "alice" });
  expect(hook.result.current.draft?.title).toBe("Alice private");
});
it("waits for catalog without replacing a recovered draft with defaults", () => {
  const first = renderHook(() => useDrafts(catalog, session()));
  act(() =>
    first.result.current.update({
      ...first.result.current.draft!,
      title: "Saved",
    }),
  );
  first.unmount();
  const next = renderHook(({ data }) => useDrafts(data, session()), {
    initialProps: { data: null as Catalog | null },
  });
  next.rerender({ data: catalog });
  expect(next.result.current.draft?.title).toBe("Saved");
});
it("keeps independent drafts when a template disappears and returns", () => {
  const first = renderHook(({ data }) => useDrafts(data, session()), {
    initialProps: { data: catalog },
  });
  act(() =>
    first.result.current.update({
      ...first.result.current.draft!,
      title: "Template edits",
    }),
  );
  act(() => first.result.current.choose("custom"));
  act(() =>
    first.result.current.update({
      ...first.result.current.draft!,
      title: "Custom edits",
    }),
  );
  act(() => first.result.current.setStep(1));
  act(() => first.result.current.choose("student_card"));
  const reduced = { ...catalog, scenarios: { custom: sample.scenario } };
  first.rerender({ data: reduced });
  expect(first.result.current.draft?.title).toBe("Custom edits");
  expect(first.result.current.step).toBe(0);
  expect(first.result.current.status).toContain(
    "Прежний шаблон больше недоступен",
  );
  first.unmount();

  // Older clients reject the entire v1 record if it references an absent template.
  const key = "dvoinik:drafts:v1:alice";
  const legacy = JSON.parse(sessionStorage.getItem(key)!);
  expect(legacy.activeKey).toBe("custom");
  expect(Object.keys(legacy.drafts)).toEqual(["custom"]);
  expect(Object.keys(legacy.steps)).toEqual(["custom"]);
  legacy.drafts.custom.title = "Edited during rollback";
  sessionStorage.setItem(key, JSON.stringify(legacy));

  const restored = renderHook(() => useDrafts(catalog, session()));
  expect(restored.result.current.draft?.title).toBe("Edited during rollback");
  act(() => restored.result.current.choose("student_card"));
  expect(restored.result.current.draft?.title).toBe("Template edits");
});
it("ignores corrupt storage with a visible explanation", () => {
  const first = renderHook(() => useDrafts(catalog, session()));
  first.unmount();
  const key = sessionStorage.key(0)!;
  sessionStorage.setItem(
    key,
    '{"version":1,"activeKey":"custom","drafts":{"custom":{}}}',
  );
  const next = renderHook(() => useDrafts(catalog, session()));
  expect(next.result.current.draft?.title).toBe(sample.scenario.title);
  expect(next.result.current.status).toMatch(/восстановить/);
});
it.each([true, false])(
  "keeps both drafts until a choice after rollback (restore: %s)",
  (restore) => {
    const key = "dvoinik:drafts:v1:alice";
    const earlier = {
      ...draftFromScenario(sample.scenario, "student_card"),
      title: "Before rollback",
    };
    const current = draftFromScenario(sample.scenario, "student_card");
    const snapshot = {
      version: 1,
      owner: "alice",
      activeKey: "student_card",
      steps: {},
    };
    sessionStorage.setItem(
      key,
      JSON.stringify({ ...snapshot, drafts: { student_card: current } }),
    );
    sessionStorage.setItem(
      "dvoinik:drafts:v1:dormant:alice",
      JSON.stringify({ ...snapshot, drafts: { student_card: earlier } }),
    );

    const first = renderHook(() => useDrafts(catalog, session()));
    expect(first.result.current.draft?.title).toBe(current.title);
    expect(first.result.current.backups[0]?.title).toBe("Before rollback");
    first.unmount();
    const next = renderHook(() => useDrafts(catalog, session()));
    expect(next.result.current.backups[0]?.title).toBe("Before rollback");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    act(() => next.result.current.resolveBackup(restore));
    expect(next.result.current.draft?.title).toBe(current.title);
    confirm.mockReturnValue(true);
    act(() => next.result.current.resolveBackup(restore));
    const selectedTitle = restore ? earlier.title : current.title;
    expect(next.result.current.draft?.title).toBe(selectedTitle);
    expect(next.result.current.backups[0]).toBeUndefined();
    next.unmount();
    const restored = renderHook(() => useDrafts(catalog, session()));
    expect(restored.result.current.draft?.title).toBe(selectedTitle);
    expect(restored.result.current.backups[0]).toBeUndefined();
  },
);
it("shows the write failure alongside the warning about a missing template", () => {
  const first = renderHook(() => useDrafts(catalog, session()));
  first.unmount();
  const key = "dvoinik:drafts:v1:alice";
  const saved = sessionStorage.getItem(key);
  const setItem = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (
    this: Storage,
    name,
    value,
  ) {
    if (name === key) throw new Error("quota");
    setItem.call(this, name, value);
  });
  const reduced = { ...catalog, scenarios: { custom: sample.scenario } };
  const next = renderHook(() => useDrafts(reduced, session()));
  expect(next.result.current.status).toContain(
    "Прежний шаблон больше недоступен",
  );
  expect(next.result.current.status).toContain("Черновик не сохранён");
  expect(sessionStorage.getItem(key)).toBe(saved);
  expect(sessionStorage.getItem("dvoinik:drafts:v1:dormant:alice")).toContain(
    "student_card",
  );
});
it("keeps a third draft through a second rollback and a rejected choice", () => {
  const first = draftFromScenario(sample.scenario, "student_card");
  const base = { version: 1, owner: "alice", activeKey: first.key, steps: {} };
  for (const [suffix, title] of [
    ["alice", "Current"],
    ["dormant:alice", "During rollback"],
    ["backup:alice", "Before rollback"],
  ]) {
    sessionStorage.setItem(
      "dvoinik:drafts:v1:" + suffix,
      JSON.stringify({
        ...base,
        drafts: { [first.key]: { ...first, title } },
      }),
    );
  }
  const initial = renderHook(() => useDrafts(catalog, session()));
  initial.unmount();
  // The previous client may remove its own key on a routine save.
  sessionStorage.removeItem("dvoinik:drafts:v1:backup:alice");
  const reopened = renderHook(() => useDrafts(catalog, session()));
  expect(reopened.result.current.backups[0]?.title).toBe("Before rollback");
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const setItem = Storage.prototype.setItem;
  const quota = vi
    .spyOn(Storage.prototype, "setItem")
    .mockImplementation(function (this: Storage, key, value) {
      if (key === "dvoinik:drafts:v1:alice") throw new Error("quota");
      setItem.call(this, key, value);
    });
  act(() => reopened.result.current.resolveBackup(true));
  expect(reopened.result.current.draft?.title).toBe("Current");
  expect(reopened.result.current.backups[0]?.title).toBe("Before rollback");
  quota.mockRestore();
  act(() => reopened.result.current.resolveBackup(true));
  expect(reopened.result.current.draft?.title).toBe("Before rollback");
  expect(reopened.result.current.backups[0]?.title).toBe("During rollback");
});
it("keeps editing available when browser storage fails", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("quota");
  });
  const hook = renderHook(() => useDrafts(catalog, session()));
  act(() =>
    hook.result.current.update({
      ...hook.result.current.draft!,
      title: "Not lost in memory",
    }),
  );
  expect(hook.result.current.draft?.title).toBe("Not lost in memory");
  expect(hook.result.current.status).toMatch(/не сохранён/);
});
it("preserves custom work when replacement is declined and replaces explicitly", () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const hook = renderHook(() => useDrafts(catalog, session()));
  act(() => hook.result.current.choose("custom"));
  act(() =>
    hook.result.current.update({
      ...hook.result.current.draft!,
      title: "Existing custom",
    }),
  );
  const replacement = {
    ...draftFromScenario(sample.scenario, "custom"),
    title: "Next iteration",
  };
  let accepted: boolean | undefined;
  act(() => {
    accepted = hook.result.current.reuseDraft(replacement);
  });
  expect(accepted).toBe(false);
  expect(hook.result.current.draft?.title).toBe("Existing custom");
  confirm.mockReturnValue(true);
  act(() => {
    accepted = hook.result.current.reuseDraft(replacement);
  });
  expect(accepted).toBe(true);
  expect(hook.result.current.draft?.title).toBe("Next iteration");
});
it("resets only the selected draft after explicit confirmation", () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const hook = renderHook(() => useDrafts(catalog, session()));
  act(() =>
    hook.result.current.update({
      ...hook.result.current.draft!,
      title: "Keep",
    }),
  );
  act(() => hook.result.current.reset());
  expect(hook.result.current.draft?.title).toBe("Keep");
  confirm.mockReturnValue(true);
  act(() => hook.result.current.reset());
  expect(hook.result.current.draft?.title).toBe(sample.scenario.title);
  expect(hook.result.current.step).toBe(0);
});
it("clears draft storage on logout while leaving unrelated data", async () => {
  const drafts = renderHook(() => useDrafts(catalog, session()));
  drafts.unmount();
  expect(sessionStorage.length).toBeGreaterThan(0);
  sessionStorage.setItem("unrelated", "keep");
  vi.spyOn(api, "request").mockImplementation(
    <T,>() => Promise.resolve(session()) as Promise<T>,
  );
  const auth = renderHook(() => useSession());
  await act(async () => {});
  await act(async () => auth.result.current.logout());
  expect(sessionStorage.length).toBe(1);
  expect(sessionStorage.getItem("unrelated")).toBe("keep");
});
it("clears stored drafts when the session expires", async () => {
  const drafts = renderHook(() => useDrafts(catalog, session()));
  drafts.unmount();
  expect(sessionStorage.length).toBeGreaterThan(0);
  vi.spyOn(api, "request").mockImplementation(
    <T,>() => Promise.resolve(session()) as Promise<T>,
  );
  renderHook(() => useSession());
  await act(async () => {});
  act(() => api.onUnauthorized("Expired", 401));
  expect(sessionStorage.length).toBe(0);
});

it("clears this tab's drafts when another tab changes session", async () => {
  let receive: ((event: { data: string }) => void) | null = null;
  class Channel {
    set onmessage(callback: (event: { data: string }) => void) {
      receive = callback;
    }
    postMessage() {}
    close() {}
  }
  vi.stubGlobal("BroadcastChannel", Channel);
  const drafts = renderHook(() => useDrafts(catalog, session()));
  drafts.unmount();
  expect(sessionStorage.length).toBeGreaterThan(0);
  vi.spyOn(api, "request").mockImplementation(
    <T,>() => Promise.resolve(session("bob")) as Promise<T>,
  );
  const auth = renderHook(() => useSession());
  await act(async () => {});
  await act(async () => receive?.({ data: "session-changed" }));
  expect(sessionStorage.length).toBe(0);
  expect(auth.result.current.session?.user.id).toBe("bob");
});
it("a rejected storage read still leaves the form editable", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("denied");
  });
  const hook = renderHook(() => useDrafts(catalog, session()));
  expect(hook.result.current.status).toContain("восстановить");
  act(() =>
    hook.result.current.update({
      ...hook.result.current.draft!,
      title: "Editable",
    }),
  );
  expect(hook.result.current.draft?.title).toBe("Editable");
});
