import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, ShieldCheck, UserRound } from "lucide-react";
import { api, ignored, message } from "./api";
import { Brand, Button, Heading, Notice } from "./components";
import type { User } from "./types";
export function Login({
  onSubmit,
  busy,
  error,
}: {
  onSubmit: (username: string, password: string) => void;
  busy: boolean;
  error: string;
}) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!busy) onSubmit(username, password);
  };
  return (
    <main className="login-page">
      <section className="login-story">
        <Brand />
        <div>
          <span className="mini-label">Лаборатория клиентов</span>
          <h1>
            Сначала
            <br />
            проверьте идею.
          </h1>
          <p>
            Сравнивайте банковские предложения на синтетической аудитории и
            готовьте вопросы для живого исследования.
          </p>
          <div className="login-twins" aria-hidden="true">
            <span>А</span>
            <span>Т</span>
            <span>В</span>
            <span>Н</span>
            <i />
          </div>
          <p className="login-footnote">
            Разные сегменты. Разные решения.
            <br />
            Объяснения, с которыми можно работать.
          </p>
        </div>
        <small>Двойник · MISIS X</small>
      </section>
      <section className="login-form">
        <form onSubmit={submit}>
          <span className="login-symbol">
            <ShieldCheck size={25} />
          </span>
          <h2>Ваше рабочее пространство</h2>
          <p>Исследования доступны владельцу учётной записи.</p>
          {error && <Notice kind="error">{error}</Notice>}
          <label className="field">
            <span>Логин</span>
            <input
              autoComplete="username"
              name="username"
              required
              maxLength={80}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Пароль</span>
            <input
              type="password"
              autoComplete="current-password"
              name="password"
              required
              maxLength={256}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <Button kind="primary" type="submit" disabled={busy}>
            {busy ? "Входим…" : "Войти"}
            <ArrowRight size={18} />
          </Button>
          <small>
            Учётную запись создаёт администратор команды.
            <br />
            Если забыли пароль, обратитесь к нему.
          </small>
        </form>
      </section>
    </main>
  );
}
export function Administration({
  current,
  onError,
}: {
  current: User;
  onError: (e: unknown) => void;
}) {
  const [users, setUsers] = useState<(User & { active: number | boolean })[]>(
      [],
    ),
    [busy, setBusy] = useState<string | null>(null);
  const load = () =>
    api
      .request<{ users: (User & { active: number | boolean })[] }>("/users")
      .then((r) => setUsers(r.users));
  useEffect(() => {
    let alive = true;
    api
      .request<{ users: (User & { active: number | boolean })[] }>("/users")
      .then((r) => {
        if (alive) setUsers(r.users);
      })
      .catch((e) => {
        if (alive && !ignored(e)) onError(e);
      });
    return () => {
      alive = false;
    };
  }, []);
  const toggle = async (user: User & { active: number | boolean }) => {
    setBusy(user.id);
    try {
      await api.request("/users/" + user.id + "/active", "PUT", {
        active: !user.active,
      });
      await load();
    } catch (e) {
      if (!ignored(e)) onError(e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <Heading
        title="Доступ команды"
        description="Управляйте доступом к сервису. Архив каждого пользователя остаётся личным."
      />
      <div className="user-list">
        {users.map((u) => (
          <article key={u.id}>
            <span className="segment-avatar">
              <UserRound size={21} />
            </span>
            <div>
              <strong>{u.name}</strong>
              <small>
                {u.username} ·{" "}
                {u.role === "admin" ? "Администратор" : "Исследователь"}
                {u.id === current.id ? " · Вы" : ""}
              </small>
            </div>
            <span className={u.active ? "status-active" : "status-off"}>
              {u.active ? "Активен" : "Отключён"}
            </span>
            <Button disabled={busy !== null} onClick={() => toggle(u)}>
              {busy === u.id ? "Меняем…" : u.active ? "Отключить" : "Включить"}
            </Button>
          </article>
        ))}
      </div>
      <details className="disclosure">
        <summary>Создание аккаунта и смена пароля</summary>
        <div className="disclosure-content">
          <p>
            Эти действия выполняет администратор в терминале сервера через
            скрытый ввод. Пароль не размещается в коде или Git.
          </p>
          <code>
            python manage.py create-user --username colleague --name Имя
          </code>
          <br />
          <code>python manage.py reset-password --username colleague</code>
        </div>
      </details>
    </>
  );
}
