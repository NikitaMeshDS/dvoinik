import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, ApiError, StaleResponse } from "./api";
import type { Session } from "./types";
const session: Session = {
  user: { id: "user-a", username: "qa", name: "QA", role: "analyst" },
  csrf_token: "csrf-a",
  mode: "local",
  model: "Model",
};
beforeEach(() => {
  api.reset();
  api.onUnauthorized = vi.fn();
});
afterEach(() => {
  vi.unstubAllGlobals();
  api.reset();
});
it("discards a successful response from a previous account after a session switch", async () => {
  let finish!: (r: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    ),
  );
  api.setSession(session);
  const old = api.request("/experiments");
  api.setSession({ ...session, user: { ...session.user, id: "user-b" } });
  finish(
    new Response(JSON.stringify({ records: [{ id: "private-a" }] }), {
      status: 200,
    }),
  );
  await expect(old).rejects.toBeInstanceOf(StaleResponse);
  expect(api.onUnauthorized).not.toHaveBeenCalled();
});
it("a late unauthorized response cannot log out a newer session", async () => {
  let finish!: (r: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    ),
  );
  const old = api.request("/experiments");
  api.setSession(session);
  finish(new Response(JSON.stringify({ detail: "expired" }), { status: 401 }));
  await expect(old).rejects.toBeInstanceOf(StaleResponse);
  expect(api.onUnauthorized).not.toHaveBeenCalled();
});
it("storage failure during logout does not clear authorization and successful mutations carry CSRF", async () => {
  const fetch = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: "Storage unavailable" }), {
      status: 503,
    }),
  );
  vi.stubGlobal("fetch", fetch);
  api.setSession(session);
  await expect(api.request("/logout", "POST")).rejects.toBeInstanceOf(ApiError);
  expect(api.onUnauthorized).not.toHaveBeenCalled();
  expect(fetch.mock.calls[0][1].headers["X-CSRF-Token"]).toBe("csrf-a");
});

it("closes the workspace when the server cannot verify access instead of retaining private cached data", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: "Хранилище доступа недоступно.",
          code: "access_unavailable",
        }),
        { status: 503 },
      ),
    ),
  );
  api.setSession(session);
  await expect(api.request("/experiments")).rejects.toBeInstanceOf(ApiError);
  expect(api.onUnauthorized).toHaveBeenCalled();
});

it("failed logout keeps its retry gate even when access storage is temporarily unavailable", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: "Хранилище доступа недоступно.",
          code: "access_unavailable",
        }),
        { status: 503 },
      ),
    ),
  );
  api.setSession(session);
  await expect(api.request("/logout", "POST")).rejects.toBeInstanceOf(ApiError);
  expect(api.onUnauthorized).not.toHaveBeenCalled();
});
