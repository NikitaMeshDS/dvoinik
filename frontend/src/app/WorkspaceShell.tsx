import { useLayoutEffect, useRef, type ReactNode } from "react";
import {
  FlaskConical,
  Plus,
  BookOpen,
  ArrowUpRight,
  Shield,
  LogOut,
  X,
} from "lucide-react";
import { Brand, Menu } from "../components";
import type { Session } from "../types";
const NAVIGATION = [
  { path: "archive", label: "Исследования", icon: FlaskConical },
  { path: "create", label: "Новое исследование", icon: Plus },
  { path: "methodology", label: "Методология", icon: BookOpen },
];
export default function WorkspaceShell({
  session,
  route,
  navigate,
  onLogout,
  toast,
  onDismiss,
  children,
}: {
  session: Session;
  route: string;
  navigate: (path: string) => void;
  onLogout: () => void;
  toast: string;
  onDismiss: () => void;
  children: ReactNode;
}) {
  const main = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    main.current?.focus({ preventScroll: true });
  }, [route]);
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
          {NAVIGATION.map(({ path, label, icon: Icon }) => {
            return (
              <a
                key={path}
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
                <Icon size={19} />
                <span>{label}</span>
              </a>
            );
          })}
        </nav>
        <div className="nav-bottom">
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
      <main className="workspace" ref={main} tabIndex={-1}>
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
                <button onClick={onLogout}>
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
            <button aria-label="Закрыть сообщение" onClick={onDismiss}>
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
          {children}
        </div>
        <footer className="app-footer">
          <span>Двойник · MISIS X</span>
          <span>
            Синтетические ответы помогают готовить живые исследования.
          </span>
        </footer>
      </main>
    </div>
  );
}
