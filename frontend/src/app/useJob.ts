import { useEffect, useReducer, useRef, useState } from "react";
import { api, ApiError, ignored, message } from "../api";
import type { Job } from "../types";
import { RequestScope } from "../shared/requests";
export function activeJob(job: Job) {
  return ["queued", "running", "cancelling"].includes(job.status);
}
/** Session-scoped monitoring continues across navigation; routing belongs to Workspace. */
export function useJob(route: string, onFinished: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null),
    [active, setActive] = useState<Job | null>(null),
    [error, setError] = useState("");
  const [revision, refresh] = useReducer((value: number) => value + 1, 0);
  const observed = useRef(new Set<string>()),
    delivered = useRef(new Set<string>()),
    finish = useRef(onFinished),
    currentRoute = useRef(route),
    currentScope = useRef<RequestScope | null>(null);
  finish.current = onFinished;
  currentRoute.current = route;
  const publish = (value: Job) => {
    if (currentRoute.current === "job/" + value.id) setJob(value);
    if (!activeJob(value)) {
      observed.current.delete(value.id);
      if (!delivered.current.has(value.id)) {
        delivered.current.add(value.id);
        finish.current(value);
      }
    }
  };
  const publishRef = useRef(publish);
  publishRef.current = publish;
  const accept = (value: Job) => {
    // A confirmed mutation invalidates older progress reads before UI commit.
    currentScope.current?.cancel();
    if (activeJob(value)) observed.current.add(value.id);
    setActive((previous) =>
      previous && previous.id !== value.id
        ? previous
        : activeJob(value)
          ? value
          : null,
    );
    publishRef.current(value);
    refresh();
  };
  useEffect(() => {
    setError("");
    const requested = route.startsWith("job/") ? route.slice(4) : null,
      scope = new RequestScope();
    currentScope.current = scope;
    let alive = true,
      timer = 0;
    const poll = async () => {
      try {
        await scope.run(
          async (signal) => {
            const { jobs } = await api.request<{ jobs: Job[] }>(
              "/runs",
              "GET",
              undefined,
              signal,
            );
            const ids = new Set(observed.current);
            if (requested) ids.add(requested);
            const details = await Promise.all(
              [...ids].map(async (id) => {
                try {
                  const value =
                    jobs.find((candidate) => candidate.id === id) ??
                    (await api.request<Job>(
                      "/runs/" + encodeURIComponent(id),
                      "GET",
                      undefined,
                      signal,
                    ));
                  return { id, value, error: null };
                } catch (e) {
                  if (ignored(e) || (e instanceof ApiError && e.authBlocked))
                    throw e;
                  return { id, value: null, error: e };
                }
              }),
            );
            return { current: jobs[0] ?? null, details };
          },
          ({ current, details }) => {
            // Successful discovery is authoritative even if a historical detail
            // is gone after restart or temporarily unavailable.
            setActive(current);
            if (current) observed.current.add(current.id);
            const errors: string[] = [];
            for (const detail of details) {
              if (detail.value) publishRef.current(detail.value);
              else {
                errors.push(message(detail.error));
                if (
                  detail.error instanceof ApiError &&
                  detail.error.status === 404
                ) {
                  observed.current.delete(detail.id);
                  if (requested === detail.id) setJob(null);
                }
              }
            }
            setError(errors.join(" "));
          },
          (e) => {
            if (!ignored(e)) setError(message(e));
          },
        );
      } catch {
        // RequestScope suppresses effects from a prior route/workspace.
      } finally {
        if (alive) timer = window.setTimeout(poll, requested ? 700 : 2000);
      }
    };
    void poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
      scope.cancel();
      if (currentScope.current === scope) currentScope.current = null;
    };
  }, [route, revision]);
  return {
    job: route === "job/" + job?.id ? job : null,
    active,
    error,
    refresh,
    accept,
  };
}
