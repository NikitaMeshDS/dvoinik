import { useEffect, useRef, useState } from "react";
import { api, ignored, message } from "../../api";
import type { Experiment } from "../../types";
import type { Insights } from "./types";
import { RequestScope } from "../../shared/requests";
type Snapshot = {
  record: Experiment;
  segment: string;
  data: Insights | null;
  error: string;
};
export function useInsights(record: Experiment, segment: string) {
  const [baseState, setBaseState] = useState<Snapshot | null>(null),
    [focusState, setFocusState] = useState<Snapshot | null>(null);
  const [baseAttempt, setBaseAttempt] = useState(0),
    [focusAttempt, setFocusAttempt] = useState(0);
  const baseScope = useRef(new RequestScope()),
    focusScope = useRef(new RequestScope());
  useEffect(() => {
    setBaseState(null);
    baseScope.current
      .run(
        (signal) =>
          api.request<Insights>(
            "/insights",
            "POST",
            { record_id: record.id, segment: "all" },
            signal,
          ),
        (data) => setBaseState({ record, segment: "all", data, error: "" }),
        (e) => {
          if (!ignored(e))
            setBaseState({
              record,
              segment: "all",
              data: null,
              error: message(e),
            });
        },
      )
      .catch(() => {});
    return () => baseScope.current.cancel();
  }, [record, baseAttempt]);
  useEffect(() => {
    setFocusState(null);
    if (segment === "all") return;
    focusScope.current
      .run(
        (signal) =>
          api.request<Insights>(
            "/insights",
            "POST",
            { record_id: record.id, segment },
            signal,
          ),
        (data) => setFocusState({ record, segment, data, error: "" }),
        (e) => {
          if (!ignored(e))
            setFocusState({ record, segment, data: null, error: message(e) });
        },
      )
      .catch(() => {});
    return () => focusScope.current.cancel();
  }, [segment, record, focusAttempt]);
  // Do not show the previous audience or record between render and effect cleanup.
  const base = baseState?.record === record ? baseState.data : null;
  const baseError = baseState?.record === record ? baseState.error : "";
  const currentFocus =
    focusState?.record === record && focusState.segment === segment
      ? focusState
      : null;
  const focus = segment === "all" ? base : (currentFocus?.data ?? null);
  const focusError =
    segment === "all" ? baseError : (currentFocus?.error ?? "");
  return {
    base,
    focus,
    baseError,
    focusError,
    error: baseError || focusError,
    retry: () => {
      if (baseError) setBaseAttempt((p) => p + 1);
      if (segment !== "all" && focusError) setFocusAttempt((p) => p + 1);
    },
  };
}
