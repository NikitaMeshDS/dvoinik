/**
 * Онлайн-витрина: обслуживает запросы /api из готовых данных без сервера.
 *
 * Данные строит scripts/build_showcase.py теми же функциями, что и локальный
 * сервис. Запускаются только шаблоны без изменений в демо-режиме; остальное
 * (свой сценарий, опрос, сравнение, скачивания) честно отклоняется с подсказкой.
 */
import type { Experiment, Scenario } from "../types";

type Data = {
  session: unknown;
  catalog: { scenarios: Record<string, Scenario>; segments: unknown };
  sizes: number[];
  seed: number;
  records: Record<string, Experiment>;
  experiments?: { scenario: Scenario; n: number; record: Experiment }[];
  insights: Record<string, unknown>;
  estimate: {
    system_chars: number;
    baseline_chars: number;
    chars_per_token: number;
    output_tokens: number;
    profile_chars: number;
    latency_s: number;
  };
  templates: Record<string, Scenario>;
};
type Job = {
  id: string;
  status: string;
  done: number;
  total: number;
  record?: Experiment | null;
  saved?: boolean;
  error?: string | null;
  polls: number;
};

export const LOCAL_HINT =
  "Полная версия запускается локально: github.com/NikitaMeshDS/dvoinik";
const ONLY_TEMPLATES =
  "Онлайн-витрина запускает готовые шаблоны без изменений в демо-режиме (seed 42, " +
  "50–1000 двойников) и A/B-проверки предложенных гипотез на 200 двойниках. " +
  "Свой сценарий и подключённая LLM доступны в локальной версии.";

class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function normalizeShares(weights: Record<string, number>) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  if (!(total > 0))
    throw new HttpError(422, "Сумма долей аудитории должна быть больше нуля.");
  return Object.fromEntries(
    Object.entries(weights)
      .filter(([, w]) => w > 0)
      .map(([s, w]) => [s, w / total]),
  );
}

/** Метод наибольших остатков, как population.allocate_population. */
export function allocate(n: number, shares: Record<string, number>) {
  const expected = Object.entries(shares).map(([s, w]) => [s, n * w] as const);
  const counts: Record<string, number> = Object.fromEntries(
    expected.map(([s, v]) => [s, Math.floor(v)]),
  );
  const left = n - Object.values(counts).reduce((a, b) => a + b, 0);
  [...expected]
    .sort((a, b) => b[1] - counts[b[0]] - (a[1] - counts[a[0]]))
    .slice(0, left)
    .forEach(([s]) => (counts[s] += 1));
  return counts;
}

function same(a: Scenario, b: Scenario) {
  const text = (s: string) => s.trim();
  const shares = (p: Record<string, number>) => {
    const n = normalizeShares(p);
    return Object.fromEntries(
      Object.entries(n).map(([k, v]) => [k, Math.round(v * 1e6)]),
    );
  };
  return (
    text(a.title) === text(b.title) &&
    text(a.question) === text(b.question) &&
    text(a.description ?? "") === text(b.description ?? "") &&
    JSON.stringify(Object.entries(a.variants).map(([k, v]) => [k, text(v)])) ===
      JSON.stringify(
        Object.entries(b.variants).map(([k, v]) => [k, text(v)]),
      ) &&
    JSON.stringify(a.objections.map(text)) ===
      JSON.stringify(b.objections.map(text)) &&
    JSON.stringify(shares(a.population)) ===
      JSON.stringify(shares(b.population))
  );
}

export function createBackend(data: Data) {
  const archive: Experiment[] = [];
  const jobs = new Map<string, Job>();
  const base = new Map<string, string>();
  let counter = 0;
  const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
  const find = (id: string) => {
    const record = archive.find((r) => r.id === id);
    if (!record) throw new HttpError(404, "Исследование не найдено.");
    return record;
  };
  function estimate(scenario: Scenario, n: number, concurrency: number) {
    const e = data.estimate;
    const shared =
      e.system_chars +
      (scenario.description ?? "").length +
      scenario.question.length +
      scenario.objections.reduce((a, o) => a + o.length + 2, 0) +
      e.profile_chars +
      120;
    const variants = Object.values(scenario.variants);
    const requests = n * variants.length + 1;
    const inputChars =
      variants.reduce((a, t) => a + (shared + t.length) * n, 0) +
      e.baseline_chars +
      variants.reduce((a, t) => a + t.length + 20, 0) +
      600;
    const minutes =
      (Math.ceil(requests / Math.max(1, concurrency)) * e.latency_s) / 60;
    return {
      requests,
      input_tokens: Math.ceil(inputChars / e.chars_per_token),
      output_tokens: requests * e.output_tokens,
      minutes,
      latency_s: e.latency_s,
      concurrency,
      cost: null,
      currency: null,
      detail: `≈ по ${e.chars_per_token} символа на токен и ${e.latency_s} с на запрос при параллельности ${concurrency}. Фактические значения зависят от модели и сервера.`,
    };
  }
  function startRun(body: {
    scenario_key: string;
    scenario: Scenario;
    n: number;
    mock: boolean;
    seed: number;
  }) {
    const template = data.templates[body.scenario_key];
    const record =
      body.scenario_key === "custom"
        ? data.experiments?.find(
            (e) => e.n === body.n && same(body.scenario, e.scenario),
          )?.record
        : template && same(body.scenario, template)
          ? data.records[body.scenario_key + "|" + body.n]
          : undefined;
    if (!record || body.mock !== true || body.seed !== data.seed)
      throw new HttpError(422, ONLY_TEMPLATES);
    const id = "showcase-" + ++counter;
    const total = body.n * Object.keys(record.scenario.variants).length;
    const run = copy(record);
    run.id = record.id + "-" + counter;
    run.created_at = new Date().toISOString().replace("Z", "+00:00");
    base.set(run.id, record.id);
    jobs.set(id, {
      id,
      status: "queued",
      done: 0,
      total,
      record: run,
      polls: 0,
    });
    return { id, status: "queued", done: 0, total };
  }
  function job(id: string) {
    const j = jobs.get(id);
    if (!j) throw new HttpError(404, "Запуск не найден.");
    j.polls++;
    if (j.polls === 1)
      return { ...pub(j), status: "running", done: Math.floor(j.total / 2) };
    if (j.status !== "completed") {
      j.status = "completed";
      j.done = j.total;
      j.saved = true;
      archive.unshift(j.record!);
    }
    return { ...pub(j), record: j.record };
  }
  const pub = (j: Job) => ({
    id: j.id,
    status: j.status,
    done: j.done,
    total: j.total,
    saved: j.saved ?? false,
    error: null,
    record: null as Experiment | null,
  });
  async function handle(method: string, path: string, body: any) {
    if (path === "/session") return data.session;
    if (path === "/catalog") return data.catalog;
    if (path === "/experiments" && method === "GET")
      return { records: archive };
    if (path === "/recovery" || (path === "/runs" && method === "GET"))
      return { jobs: [] };
    if (path === "/logout") return { ok: true };
    if (path === "/preview") {
      const shares = normalizeShares(body.population);
      return { counts: allocate(body.n, shares), shares };
    }
    if (path === "/estimate")
      return estimate(body.scenario, body.n, body.concurrency ?? 16);
    if (path === "/runs" && method === "POST") return startRun(body);
    const runMatch = path.match(/^\/runs\/([^/]+)$/);
    if (runMatch && method === "GET") return job(runMatch[1]);
    if (path.startsWith("/sample/")) {
      const key = decodeURIComponent(path.slice(8));
      const record = data.records[key + "|200"];
      if (!record) throw new HttpError(404, "Шаблон исследования не найден.");
      const sample = { ...copy(record), sample: true, id: "sample-" + key };
      base.set(sample.id, record.id);
      if (!archive.some((r) => r.id === sample.id)) archive.push(sample);
      return sample;
    }
    if (path === "/insights") {
      const key =
        (base.get(body.record_id) ?? body.record_id) + "|" + body.segment;
      const value = data.insights[key];
      if (!value) throw new HttpError(404, "Аналитика не найдена.");
      return value;
    }
    const recordMatch = path.match(/^\/experiments\/([^/]+)$/);
    if (recordMatch && method === "GET")
      return find(decodeURIComponent(recordMatch[1]));
    if (path === "/hypotheses/rewrite")
      throw new HttpError(
        422,
        "Переписать текст моделью можно в локальной версии с LLM. " +
          LOCAL_HINT,
      );
    if (path.includes("/validation"))
      throw new HttpError(
        422,
        "Загрузка опроса в онлайн-витрине недоступна. " + LOCAL_HINT,
      );
    if (path.startsWith("/compare"))
      throw new HttpError(
        422,
        "Сравнение запусков доступно в локальной версии. " + LOCAL_HINT,
      );
    if (path === "/export" || path === "/import")
      throw new HttpError(
        422,
        "Скачивание и импорт доступны в локальной версии. " + LOCAL_HINT,
      );
    throw new HttpError(404, "Действие недоступно в онлайн-витрине.");
  }
  return async (method: string, path: string, body: unknown) => {
    try {
      return { status: 200, payload: await handle(method, path, body) };
    } catch (e) {
      if (e instanceof HttpError)
        return { status: e.status, payload: { detail: e.message } };
      return {
        status: 422,
        payload: { detail: e instanceof Error ? e.message : String(e) },
      };
    }
  };
}

export async function install() {
  const original = window.fetch.bind(window);
  const data = (await (await original("showcase-data.json")).json()) as Data;
  const backend = createBackend(data);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    if (!url.startsWith("/api/")) return original(input, init);
    const method = (init?.method ?? "GET").toUpperCase();
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const { status, payload } = await backend(method, url.slice(4), body);
    await new Promise((r) => setTimeout(r, 120));
    return new Response(JSON.stringify(payload), {
      status:
        status === 200 && method === "POST" && url === "/api/runs"
          ? 202
          : status,
      headers: { "Content-Type": "application/json" },
    });
  };
  const note = document.createElement("div");
  note.className = "showcase-note";
  note.textContent =
    "Онлайн-витрина · готовые шаблоны в демо-режиме · полная версия локально: github.com/NikitaMeshDS/dvoinik";
  document.body.append(note);
}
