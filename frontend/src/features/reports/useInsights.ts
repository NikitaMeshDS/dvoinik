import { useEffect, useRef, useState } from "react";
import { api, ignored, message } from "../../api";
import type { Experiment } from "../../types";
import type { Insights } from "./types";
import { RequestScope } from "../../shared/requests";
export function useInsights(record: Experiment, segment: string) {
  const [base, setBase] = useState<Insights | null>(null),
    [focus, setFocus] = useState<Insights | null>(null);
  const [baseError, setBaseError] = useState(""),
    [focusError, setFocusError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const baseScope = useRef(new RequestScope()),
    focusScope = useRef(new RequestScope());
  useEffect(() => {
    setBase(null);
    setBaseError("");
    baseScope.current
      .run((signal) =>
        api.request<Insights>(
          "/insights",
          "POST",
          { record_id: record.id, segment: "all" },
          signal,
        ),
      )
      .then(setBase)
      .catch((e) => {
        if (!ignored(e)) setBaseError(message(e));
      });
    return () => baseScope.current.cancel();
  }, [record, attempt]);
  useEffect(() => {
    setFocus(null);
    setFocusError("");
    if (segment === "all") {
      setFocus(base);
      return;
    }
    focusScope.current
      .run((signal) =>
        api.request<Insights>(
          "/insights",
          "POST",
          { record_id: record.id, segment },
          signal,
        ),
      )
      .then(setFocus)
      .catch((e) => {
        if (!ignored(e)) setFocusError(message(e));
      });
    return () => focusScope.current.cancel();
  }, [segment, base, record.id, attempt]);
  return {
    base,
    focus,
    error: baseError || focusError,
    retry: () => setAttempt((p) => p + 1),
  };
}
