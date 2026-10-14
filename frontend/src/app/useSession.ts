import { useEffect, useRef, useState } from "react";
import { api, ApiError, ignored, message } from "../api";
import type { Session } from "../types";
/** Authentication owns the lifetime of a workspace, never its research data. */
export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [booting, setBooting] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [logoutBlocked, setLogoutBlocked] = useState("");
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const channel = useRef<BroadcastChannel | null>(null);
  const clear = () => {
    api.reset();
    setSession(null);
    setLogoutBlocked("");
    window.location.hash = "/archive";
  };
  useEffect(() => {
    let alive = true,
      load = 0;
    api.onUnauthorized = (detail, status) => {
      const hadSession = sessionRef.current !== null;
      clear();
      setBooting(false);
      setError(
        status === 401 && !hadSession
          ? ""
          : (detail ?? "Сессия завершена. Войдите снова."),
      );
    };
    const refresh = () => {
      const ticket = ++load;
      setBooting(true);
      api
        .request<Session>("/session")
        .then((value) => {
          if (alive && ticket === load) {
            api.setSession(value);
            setSession(value);
            setError("");
          }
        })
        .catch((e) => {
          if (
            alive &&
            ticket === load &&
            !ignored(e) &&
            !(e instanceof ApiError && e.authBlocked)
          )
            setError(message(e));
        })
        .finally(() => {
          if (alive && ticket === load) setBooting(false);
        });
    };
    if ("BroadcastChannel" in window) {
      channel.current = new BroadcastChannel("dvoinik-access");
      channel.current.onmessage = (event) => {
        if (event.data === "session-changed") {
          clear();
          refresh();
        }
      };
    }
    refresh();
    return () => {
      alive = false;
      channel.current?.close();
      channel.current = null;
      api.onUnauthorized = () => {};
    };
  }, []);
  const login = async (username: string, password: string) => {
    setBusy(true);
    setError("");
    try {
      const value = await api.request<Session>("/login", "POST", {
        username,
        password,
      });
      api.setSession(value);
      setSession(value);
      window.location.hash = "/archive";
      channel.current?.postMessage("session-changed");
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  const logout = async () => {
    setLogoutBlocked("Выходим из рабочего пространства…");
    try {
      await api.request("/logout", "POST");
      channel.current?.postMessage("session-changed");
      clear();
      setError("");
    } catch (e) {
      if (!ignored(e) && !(e instanceof ApiError && e.status === 401))
        setLogoutBlocked(message(e));
    }
  };
  return { session, booting, busy, error, logoutBlocked, login, logout };
}
