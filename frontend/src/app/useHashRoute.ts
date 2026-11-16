import { useCallback, useEffect, useState } from "react";
const current = () => window.location.hash.replace(/^#\/?/, "") || "archive";
export function useHashRoute() {
  const [route, setRoute] = useState(current);
  useEffect(() => {
    const changed = () => setRoute(current());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  const navigate = useCallback((path: string) => {
    if (
      !window.dispatchEvent(
        new CustomEvent("dvoinik:before-leave", {
          cancelable: true,
          detail: { path },
        }),
      )
    )
      return;
    window.location.hash = "/" + path;
    setRoute(path);
  }, []);
  return { route, navigate };
}
