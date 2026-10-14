import { useEffect, useReducer, useRef, useState } from "react";
import { api, ignored, message } from "../api";
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
  const previous = useRef<Job | null>(null),
    delivered = useRef(new Set<string>()),
    finish = useRef(onFinished);
  finish.current = onFinished;
  useEffect(() => {
    setError("");
    const requested = route.startsWith("job/") ? route.slice(4) : null,
      scope = new RequestScope();
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
            const current = jobs[0] ?? null;
            const id = requested ?? previous.current?.id;
            const value = id
              ? (jobs.find((candidate) => candidate.id === id) ??
                (await api.request<Job>(
                  "/runs/" + encodeURIComponent(id),
                  "GET",
                  undefined,
                  signal,
                )))
              : null;
            return { current, value };
          },
          ({ current, value }) => {
            previous.current = current;
            setActive(current);
            setError("");
            if (requested) setJob(value);
            if (
              value &&
              !activeJob(value) &&
              !delivered.current.has(value.id)
            ) {
              delivered.current.add(value.id);
              finish.current(value);
            }
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
    };
  }, [route, revision]);
  return {
    job: route === "job/" + job?.id ? job : null,
    active,
    error,
    refresh,
  };
}
