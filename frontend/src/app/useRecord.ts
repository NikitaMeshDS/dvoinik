import { useEffect, useRef, useState } from "react";
import { api, ignored, message } from "../api";
import type { Experiment } from "../types";
import { RequestScope } from "../shared/requests";
export function useRecord(route: string) {
  const [record, setRecord] = useState<Experiment | null>(null),
    [error, setError] = useState("");
  const scope = useRef(new RequestScope());
  const currentRoute = useRef(route);
  currentRoute.current = route;
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!route.startsWith("report/")) {
      setRecord(null);
      return;
    }
    setRecord(null);
    setError("");
    scope.current
      .run(
        (signal) =>
          api.request<Experiment>(
            "/experiments/" + encodeURIComponent(route.slice(7)),
            "GET",
            undefined,
            signal,
          ),
        setRecord,
        (e) => {
          if (!ignored(e)) setError(message(e));
        },
      )
      .catch(() => {});
    return () => scope.current.cancel();
  }, [route, attempt]);
  const updated = (value: Experiment) => {
    if (currentRoute.current !== "report/" + value.id) return;
    scope.current.cancel();
    setRecord(value);
    setError("");
  };
  return { record, error, updated, retry: () => setAttempt((p) => p + 1) };
}
