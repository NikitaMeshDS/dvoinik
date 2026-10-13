import type { Session } from "./types";
export class ApiError extends Error {
  status: number;
  authBlocked: boolean;
  constructor(message: string, status: number, authBlocked = false) {
    super(message);
    this.status = status;
    this.authBlocked = authBlocked;
  }
}
export class StaleResponse extends Error {
  constructor() {
    super("Ответ предыдущего рабочего пространства.");
  }
}
class Api {
  private csrf = "";
  private epoch = 0;
  onUnauthorized: (detail?: string) => void = () => {};
  reset() {
    this.csrf = "";
    this.epoch++;
  }
  setSession(session: Session) {
    this.csrf = session.csrf_token;
    this.epoch++;
  }
  async request<T>(
    path: string,
    method = "GET",
    body?: unknown,
    signal?: AbortSignal,
  ): Promise<T> {
    const epoch = this.epoch;
    let response: Response;
    try {
      response = await fetch("/api" + path, {
        method,
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          ...(this.csrf ? { "X-CSRF-Token": this.csrf } : {}),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal,
      });
    } catch (e) {
      if (signal?.aborted) throw e;
      if (epoch !== this.epoch) throw new StaleResponse();
      throw new ApiError(
        "Сервис не отвечает. Проверьте соединение и повторите действие.",
        0,
      );
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = { detail: "Сервис вернул неожиданный ответ." };
    }
    if (epoch !== this.epoch) throw new StaleResponse();
    if (!response.ok) {
      const data = payload as { detail?: unknown; code?: unknown };
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : "Не удалось выполнить действие.";
      const authBlocked =
        response.status === 401 ||
        (data.code === "access_unavailable" && path !== "/logout");
      if (authBlocked) {
        this.reset();
        this.onUnauthorized(detail);
      }
      throw new ApiError(detail, response.status, authBlocked);
    }
    return payload as T;
  }
}
export const api = new Api();
export async function download(path: string, body: unknown) {
  const { url } = await api.request<{ url: string }>(path, "POST", body);
  const target = new URL(url, window.location.origin);
  if (
    target.origin !== window.location.origin ||
    !target.pathname.startsWith("/download/")
  )
    throw new ApiError("Неверная ссылка скачивания.", 0);
  const a = document.createElement("a");
  a.href = target.href;
  a.rel = "noreferrer";
  a.referrerPolicy = "no-referrer";
  a.download = "";
  a.hidden = true;
  document.body.append(a);
  a.click();
  a.remove();
}
export function ignored(error: unknown) {
  return (
    error instanceof StaleResponse ||
    (error instanceof DOMException && error.name === "AbortError")
  );
}
export function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Не удалось выполнить действие.";
}
