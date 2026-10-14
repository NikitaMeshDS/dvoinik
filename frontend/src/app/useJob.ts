import { useEffect, useRef, useState } from "react";
import { api, ignored, message } from "../api";
import type { Job } from "../types";
import { RequestScope } from "../shared/requests";
export function useJob(route: string, onCompleted: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null);
  const complete = useRef(onCompleted);
  complete.current = onCompleted;
  useEffect(() => {
    setJob(null);
    if (!route.startsWith("job/")) return;
    const id = route.slice(4),
      scope = new RequestScope();
    let alive = true,
      timer = 0;
    const poll = async () => {
      try {
        const value = await scope.run((signal) =>
          api.request<Job>(
            "/runs/" + encodeURIComponent(id),
            "GET",
            undefined,
            signal,
          ),
        );
        if (!alive) return;
        setJob(value);
        if (value.status === "completed" && value.record)
          complete.current(value);
        else if (value.status !== "failed")
          timer = window.setTimeout(poll, 700);
      } catch (e) {
        if (alive && !ignored(e))
          setJob({
            id,
            status: "failed",
            done: 0,
            total: 1,
            error: message(e),
          });
      }
    };
    void poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
      scope.cancel();
    };
  }, [route]);
  return job;
}
