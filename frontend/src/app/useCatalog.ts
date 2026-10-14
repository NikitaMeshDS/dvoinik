import { useEffect, useRef, useState } from "react";
import { api, ignored, message } from "../api";
import type { Catalog } from "../types";
import { RequestScope } from "../shared/requests";
export function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0),
    scope = useRef(new RequestScope());
  useEffect(() => {
    setError("");
    scope.current
      .run(
        (signal) => api.request<Catalog>("/catalog", "GET", undefined, signal),
        setCatalog,
        (e) => {
          if (!ignored(e)) setError(message(e));
        },
      )
      .catch(() => {});
    return () => scope.current.cancel();
  }, [attempt]);
  return { catalog, error, retry: () => setAttempt((p) => p + 1) };
}
