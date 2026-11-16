import { useEffect, useRef } from "react";

const WARNING = "Предпросмотр опроса ещё не сохранён. Уйти и потерять его?";
const path = (hash: string) => hash.replace(/^#\/?/, "").split("?")[0];

/** Keep the report mounted when a user declines to discard its survey preview. */
export function useUnsavedSurvey(recordId: string, dirty: boolean) {
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const leaving = useRef(false);
  const reportPath = "report/" + recordId;
  useEffect(() => {
    let acceptedUrl = window.location.href;
    const beforeLeave = (event: Event) => {
      const destination = (event as CustomEvent<{ path?: string }>).detail
        ?.path;
      if (
        !dirtyRef.current ||
        leaving.current ||
        (destination && path(destination) === reportPath)
      )
        return;
      if (!window.confirm(WARNING)) event.preventDefault();
    };
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current || leaving.current) return;
      event.preventDefault();
      event.returnValue = "";
    };
    const click = (event: MouseEvent) => {
      if (
        !dirtyRef.current ||
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const link = (event.target as Element | null)?.closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (!link || link.target === "_blank" || link.hasAttribute("download"))
        return;
      const url = new URL(link.href, window.location.href);
      if (
        url.origin === window.location.origin &&
        url.pathname === window.location.pathname &&
        path(url.hash) === reportPath
      )
        return;
      if (!window.confirm(WARNING)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      } else leaving.current = true;
    };
    const changed = (event: HashChangeEvent) => {
      if (path(window.location.hash) === reportPath) {
        acceptedUrl = window.location.href;
        leaving.current = false;
        return;
      }
      if (!dirtyRef.current || leaving.current || window.confirm(WARNING)) {
        leaving.current = true;
        return;
      }
      // Legacy entries have no history-position IDs. Add the accepted URL back
      // without replacing the destination, so a subsequent confirmed Back works.
      // Like ordinary push navigation this discards the forward branch.
      event.stopImmediatePropagation();
      window.history.pushState(window.history.state, "", acceptedUrl);
    };
    window.addEventListener("dvoinik:before-leave", beforeLeave);
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", click, true);
    window.addEventListener("hashchange", changed, true);
    return () => {
      window.removeEventListener("dvoinik:before-leave", beforeLeave);
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", click, true);
      window.removeEventListener("hashchange", changed, true);
    };
  }, [reportPath]);
  return (action: () => void) => {
    if (dirtyRef.current && !window.confirm(WARNING)) return;
    leaving.current = true;
    action();
    // A downstream action can itself be cancelled (for example draft replacement).
    if (path(window.location.hash) === reportPath) leaving.current = false;
  };
}
