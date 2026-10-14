import { useEffect, useRef, useState } from "react";
import {
  FlaskConical,
  Plus,
  BookOpen,
  LogOut,
  Shield,
  ArrowUpRight,
  X,
} from "lucide-react";
import { api, ignored, message, ApiError } from "./api";
import { draftFromScenario, draftFromRecord, runPayload } from "./draft";
import { comparisonOrder } from "./data";
import { Brand, Menu, Notice, Button } from "./components";
import { Login, Administration } from "./Account";
import { ImportDialog, ComparisonDialog } from "./Compare";
import Composer from "./Composer";
import Library, { INITIAL_LIBRARY, type LibraryState } from "./Library";
import Report from "./Report";
import JobView from "./JobView";
import Methodology from "./Methodology";
import type { Catalog, Draft, Experiment, Job, Session } from "./types";
const initialRoute = () =>
  window.location.hash.replace(/^#\/?/, "") || "archive";
export default function App() {
  const [session, setSession] = useState<Session | null>(null),
    [booting, setBooting] = useState(true),
    [loginBusy, setLoginBusy] = useState(false),
    [loginError, setLoginError] = useState("");
  const [route, setRoute] = useState(initialRoute),
    [catalog, setCatalog] = useState<Catalog | null>(null),
    [records, setRecords] = useState<Experiment[]>([]),
    [record, setRecord] = useState<Experiment | null>(null),
    [recordError, setRecordError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, Draft>>({}),
    [activeKey, setActiveKey] = useState("student_card"),
    [job, setJob] = useState<Job | null>(null),
    [runBusy, setRunBusy] = useState(false),
    [pending, setPending] = useState<
      Record<string, { record: Experiment; job: string; error: string }>
    >({});
  const [library, setLibrary] = useState<LibraryState>(INITIAL_LIBRARY),
    [modal, setModal] = useState<"import" | "compare" | null>(null),
    [compareIds, setCompareIds] = useState<string[]>([]),
    [toast, setToast] = useState(""),
    [logoutBlocked, setLogoutBlocked] = useState("");
  const authChannel = useRef<BroadcastChannel | null>(null);
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const pendingRef = useRef(pending);
  pendingRef.current = pending;
  const navigate = (path: string) => {
    window.location.hash = "/" + path;
    setRoute(path);
  };
  const clear = () => {
    api.reset();
    setSession(null);
    setCatalog(null);
    setRecords([]);
    setRecord(null);
    setDrafts({});
    setActiveKey("student_card");
    setJob(null);
    setRunBusy(false);
    setPending({});
    setLibrary(INITIAL_LIBRARY);
    setModal(null);
    setToast("");
    setLogoutBlocked("");
    setRoute("archive");
    window.location.hash = "/archive";
  };
  const onError = (error: unknown) => {
    if (!ignored(error) && !(error instanceof ApiError && error.authBlocked))
      setToast(message(error));
  };
  useEffect(() => {
    const changed = () => setRoute(initialRoute());
    window.addEventListener("hashchange", changed);
    api.onUnauthorized = (detail, status) => {
      const hadSession = sessionRef.current !== null;
      clear();
      setBooting(false);
      setLoginError(
        status === 401 && !hadSession
          ? ""
          : (detail ?? "Сессия завершена. Войдите снова."),
      );
    };
    let alive = true,
      authLoad = 0;
    const refresh = () => {
      const current = ++authLoad;
      setBooting(true);
      api
        .request<Session>("/session")
        .then((value) => {
          if (alive && current === authLoad) {
            api.setSession(value);
            setSession(value);
          }
        })
        .catch((e) => {
          if (
            alive &&
            current === authLoad &&
            !ignored(e) &&
            !(e instanceof ApiError && e.authBlocked)
          )
            setLoginError(message(e));
        })
        .finally(() => {
          if (alive && current === authLoad) setBooting(false);
        });
    };
    if ("BroadcastChannel" in window) {
      const channel = new BroadcastChannel("dvoinik-access");
      authChannel.current = channel;
      channel.onmessage = (event) => {
        if (event.data === "session-changed") {
          clear();
          refresh();
        }
      };
    }
    refresh();
    return () => {
      alive = false;
      window.removeEventListener("hashchange", changed);
      authChannel.current?.close();
      authChannel.current = null;
      api.onUnauthorized = () => {};
    };
  }, []);
  const loadRecords = async () => {
    const recovery = await api.request<{ jobs: Job[] }>("/recovery");
    setPending(
      Object.fromEntries(
        recovery.jobs
          .filter((j) => j.record)
          .map((j) => [
            j.record!.id,
            {
              record: j.record!,
              job: j.id,
              error: j.error ?? "Попробуйте сохранить результат ещё раз.",
            },
          ]),
      ),
    );
    const value = await api.request<{ records: Experiment[] }>("/experiments");
    setRecords(value.records);
    setPending((previous) =>
      Object.fromEntries(
        Object.entries(previous).filter(
          ([id]) => !value.records.some((r) => r.id === id),
        ),
      ),
    );
    return value.records;
  };
  useEffect(() => {
    if (!session) return;
    let alive = true;
    api
      .request<Catalog>("/catalog")
      .then((c) => {
        if (alive) {
          setCatalog(c);
          setDrafts((previous) =>
            Object.keys(previous).length
              ? previous
              : {
                  student_card: draftFromScenario(
                    c.scenarios.student_card,
                    "student_card",
                    session.default_mock !== false,
                  ),
                },
          );
        }
      })
      .catch((e) => {
        if (alive) onError(e);
      });
    loadRecords().catch((e) => {
      if (alive) onError(e);
    });
    return () => {
      alive = false;
    };
  }, [session]);
  useEffect(() => {
    if (!session || !route.startsWith("report/")) return;
    let alive = true;
    setRecord(null);
    setRecordError("");
    const id = route.slice(7);
    api
      .request<Experiment>("/experiments/" + encodeURIComponent(id))
      .then((r) => {
        if (alive) setRecord(r);
      })
      .catch((e) => {
        if (alive && !ignored(e)) {
          setRecordError(message(e));
        }
      });
    return () => {
      alive = false;
    };
  }, [route, session]);
  useEffect(() => {
    if (!session || !route.startsWith("job/")) return;
    let alive = true,
      timer = 0;
    const id = route.slice(4);
    setJob(null);
    const poll = async () => {
      try {
        const value = await api.request<Job>("/runs/" + encodeURIComponent(id));
        if (!alive) return;
        setJob(value);
        if (value.status === "completed" && value.record) {
          if (!value.saved)
            setPending((p) => ({
              ...p,
              [value.record!.id]: {
                record: value.record!,
                job: id,
                error: value.error ?? "Попробуйте сохранить результат ещё раз.",
              },
            }));
          navigate("report/" + value.record.id);
          loadRecords().catch(onError);
        } else if (value.status !== "failed") {
          timer = window.setTimeout(poll, 700);
        }
      } catch (e) {
        if (alive && !ignored(e)) {
          setJob({
            id,
            status: "failed",
            done: 0,
            total: 1,
            error: message(e),
          });
        }
      }
    };
    void poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [route, session]);
  const login = async (username: string, password: string) => {
    setLoginBusy(true);
    setLoginError("");
    try {
      const value = await api.request<Session>("/login", "POST", {
        username,
        password,
      });
      api.setSession(value);
      setSession(value);
      authChannel.current?.postMessage("session-changed");
      navigate("archive");
    } catch (e) {
      if (!ignored(e)) setLoginError(message(e));
    } finally {
      setLoginBusy(false);
    }
  };
  const logout = async () => {
    setLogoutBlocked("Выходим из рабочего пространства…");
    try {
      await api.request("/logout", "POST");
      authChannel.current?.postMessage("session-changed");
      clear();
      setLoginError("");
    } catch (e) {
      if (!ignored(e) && !(e instanceof ApiError && e.status === 401))
        setLogoutBlocked(message(e));
    }
  };
  const changeTemplate = (key: string) => {
    if (!catalog) return;
    setDrafts((previous) =>
      previous[key]
        ? previous
        : {
            ...previous,
            [key]: draftFromScenario(
              catalog.scenarios[key],
              key,
              session?.default_mock !== false,
            ),
          },
    );
    setActiveKey(key);
  };
  const reuse = () => {
    if (!record) return;
    setDrafts((p) => ({
      ...p,
      custom: draftFromRecord(record, session?.user.role === "demo"),
    }));
    setActiveKey("custom");
    navigate("create");
  };
  const start = async () => {
    const draft = drafts[activeKey];
    if (!draft || runBusy) return;
    setRunBusy(true);
    setToast("");
    try {
      const value = await api.request<Job>("/runs", "POST", runPayload(draft));
      setJob(value);
      navigate("job/" + value.id);
    } catch (e) {
      onError(e);
    } finally {
      setRunBusy(false);
    }
  };
  const openSample = async () => {
    try {
      const value = await api.request<Experiment>("/sample/student_card");
      navigate("report/" + value.id);
    } catch (e) {
      onError(e);
    }
  };
  const updated = (value: Experiment) => {
    setRecord(value);
    setRecords((p) => [...p.filter((r) => r.id !== value.id), value]);
    setPending((p) => {
      const next = { ...p };
      delete next[value.id];
      return next;
    });
  };
  const retry = async () => {
    if (!record) return;
    const item = pendingRef.current[record.id];
    if (!item) return;
    try {
      const value = await api.request<Job>(
        "/runs/" + item.job + "/retry",
        "POST",
      );
      if (value.saved && value.record) {
        updated(value.record);
        setToast("");
      } else setToast(value.error ?? "Результат пока не записан.");
    } catch (e) {
      onError(e);
    }
  };
  const allRecords = [
    ...records,
    ...Object.values(pending)
      .map((p) => p.record)
      .filter((r) => !records.some((v) => v.id === r.id)),
  ];
  const compare = (ids: string[]) => {
    setCompareIds(
      comparisonOrder(
        ids,
        record && !allRecords.some((r) => r.id === record.id)
          ? [record, ...allRecords]
          : allRecords,
      ),
    );
    setModal("compare");
  };
  const imported = (value: Experiment) => {
    updated(value);
    navigate("report/" + value.id);
  };
  if (booting)
    return (
      <div className="boot-screen">
        <Brand />
        <p role="status">Открываем рабочее пространство…</p>
      </div>
    );
  if (!session)
    return <Login onSubmit={login} busy={loginBusy} error={loginError} />;
  if (logoutBlocked)
    return (
      <div className="boot-screen">
        <Brand />
        <Notice kind="error">{logoutBlocked}</Notice>
        <Button onClick={logout}>Повторить выход</Button>
      </div>
    );
  const section = route.startsWith("report/")
    ? "Отчёт"
    : route.startsWith("job/")
      ? "Симуляция"
      : route === "create"
        ? "Новое исследование"
        : route === "admin"
          ? "Доступ команды"
          : route === "methodology"
            ? "Методология"
            : "Исследования";
  return (
    <div className="app-shell">
      <aside className="app-nav">
        <a
          href="#/archive"
          className="brand-link"
          aria-label="Двойник: исследования"
        >
          <Brand />
        </a>
        <span className="nav-caption">Лаборатория клиентов</span>
        <nav aria-label="Рабочее пространство">
          {[
            ["archive", "Исследования", FlaskConical],
            ["create", "Новое исследование", Plus],
            ["methodology", "Методология", BookOpen],
          ].map(([path, label, Icon]) => {
            const I = Icon as typeof Plus;
            return (
              <a
                key={path as string}
                href={"#/" + path}
                aria-current={
                  route === path
                    ? "page"
                    : (path === "archive" && route.startsWith("report/")) ||
                        (path === "create" && route.startsWith("job/"))
                      ? "location"
                      : undefined
                }
              >
                <I size={19} />
                <span>{label as string}</span>
              </a>
            );
          })}
        </nav>
        <div className="nav-bottom">
          <p>
            Вопросы к продукту.
            <br />
            До запуска.
          </p>
          <a
            href="https://github.com/NikitaMeshDS/dvoinik"
            target="_blank"
            rel="noreferrer"
          >
            Проект на GitHub
            <ArrowUpRight size={14} />
          </a>
        </div>
      </aside>
      <main className="workspace">
        <div className="workspace-top">
          <span>
            Рабочее пространство <i>/</i> <strong>{section}</strong>
          </span>
          <div>
            <span
              className={
                "workspace-mode " + (session.user.role === "demo" ? "demo" : "")
              }
            >
              {session.user.role === "demo" ? "Демо" : "Личный архив"}
            </span>
            <span className="user-name">{session.user.name}</span>
            {session.user.role !== "demo" && (
              <Menu label="Меню пользователя">
                {session.user.role === "admin" && (
                  <button onClick={() => navigate("admin")}>
                    <Shield size={16} />
                    Доступ команды
                  </button>
                )}
                <button onClick={logout}>
                  <LogOut size={16} />
                  Выйти
                </button>
              </Menu>
            )}
          </div>
        </div>
        {toast && (
          <div className="toast" role="alert">
            <span>{toast}</span>
            <button aria-label="Закрыть сообщение" onClick={() => setToast("")}>
              <X size={16} />
            </button>
          </div>
        )}
        <div
          className={
            "workspace-content " +
            (route.startsWith("report/") ? "report-page" : "")
          }
        >
          {!catalog ? (
            <p className="help" role="status">
              Загружаем сценарии…
            </p>
          ) : route === "create" ? (
            <Composer
              catalog={catalog}
              draft={
                drafts[activeKey] ??
                draftFromScenario(
                  catalog.scenarios[activeKey],
                  activeKey,
                  session.default_mock !== false,
                )
              }
              onChange={(draft) =>
                setDrafts((p) => ({ ...p, [activeKey]: draft }))
              }
              onTemplate={changeTemplate}
              onRun={start}
              demo={session.user.role === "demo"}
              busy={runBusy}
            />
          ) : route.startsWith("report/") ? (
            record ? (
              <Report
                key={record.id}
                record={record}
                catalog={catalog}
                onBack={() => navigate("archive")}
                onReuse={reuse}
                onUpdated={updated}
                onCompare={() => compare([record.id, ""])}
                onError={onError}
                pending={pending[record.id]?.error}
                onRetry={retry}
              />
            ) : recordError ? (
              <Notice kind="error">
                {recordError}
                <div>
                  <button
                    className="text-link"
                    onClick={() => navigate("archive")}
                  >
                    Вернуться к исследованиям
                  </button>
                </div>
              </Notice>
            ) : (
              <p className="help" role="status">
                Открываем сохранённый снимок…
              </p>
            )
          ) : route.startsWith("job/") ? (
            <JobView job={job} onBack={() => navigate("create")} />
          ) : route === "methodology" ? (
            <Methodology />
          ) : route === "admin" ? (
            session.user.role === "admin" ? (
              <Administration current={session.user} onError={onError} />
            ) : (
              <Notice kind="error">
                Управление доступом доступно администратору.
              </Notice>
            )
          ) : (
            <Library
              records={allRecords}
              state={library}
              onState={setLibrary}
              onNew={() => navigate("create")}
              onOpen={(id) => navigate("report/" + id)}
              onImport={() => setModal("import")}
              onSample={openSample}
              onCompare={compare}
              pending={new Set(Object.keys(pending))}
            />
          )}
        </div>
        <footer className="app-footer">
          <span>Двойник · MISIS X</span>
          <span>
            Синтетические ответы помогают готовить живые исследования.
          </span>
        </footer>
      </main>
      {modal === "import" && (
        <ImportDialog onClose={() => setModal(null)} onImported={imported} />
      )}
      {modal === "compare" && (
        <ComparisonDialog
          ids={compareIds}
          records={
            record && !allRecords.some((r) => r.id === record.id)
              ? [record, ...allRecords]
              : allRecords
          }
          onClose={() => setModal(null)}
          onError={onError}
        />
      )}
    </div>
  );
}
