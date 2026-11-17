import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowLeft,
  Users,
  Check,
  SlidersHorizontal,
} from "lucide-react";
import { api, ignored, message } from "./api";
import { draftError, draftIssue, type DraftIssue, runPayload } from "./draft";
import { Button, Heading, Notice, decimal } from "./components";
import {
  VARIANTS,
  TITLES,
  type Catalog,
  type Draft,
  type Estimate,
} from "./types";
import LaunchReview from "./features/composer/LaunchReview";
import RespondentPreview from "./features/composer/RespondentPreview";
import AudienceDistribution from "./features/composer/AudienceDistribution";
type Preview = {
  requestKey: string;
  counts: Record<string, number>;
  shares: Record<string, number>;
};
export default function Composer({
  catalog,
  draft,
  onChange,
  onTemplate,
  onRun,
  demo,
  busy,
  activeRun = false,
  step: controlledStep,
  onStepChange,
  draftStatus,
  onReset,
}: {
  catalog: Catalog;
  draft: Draft;
  onChange: (d: Draft) => void;
  onTemplate: (key: string) => void;
  onRun: () => void;
  demo: boolean;
  busy: boolean;
  activeRun?: boolean;
  step?: number;
  onStepChange?: (step: number) => void;
  draftStatus?: string;
  onReset?: () => void;
}) {
  const [localStep, setLocalStep] = useState(0),
    [error, setError] = useState<DraftIssue | null>(null),
    [preview, setPreview] = useState<Preview | null>(null),
    [previewError, setPreviewError] = useState(""),
    [loading, setLoading] = useState(false),
    [estimate, setEstimate] = useState<
      (Estimate & { requestKey: string }) | null
    >(null);
  const step = controlledStep ?? localStep;
  const setStep = (value: number) => {
    setLocalStep(value);
    onStepChange?.(value);
  };
  const errorId = useId();
  const stage = useRef<HTMLElement>(null);
  const fieldProps = (field: string) => ({
    "data-draft-field": field,
    "aria-label": (
      {
        title: "Название исследования",
        question: "Вопрос двойникам",
        objections: "Категории отказа — одна на строку",
        n: "Размер аудитории",
        seed: "Seed популяции и демо",
        concurrency: "Параллельных запросов LLM",
      } as Record<string, string>
    )[field],
    "aria-invalid": error?.field === field || undefined,
    "aria-describedby": error?.field === field ? errorId : undefined,
  });
  const fieldError = (field: string) =>
    error?.field === field ? (
      <span id={errorId} className="field-error" role="alert">
        {error.message}
      </span>
    ) : null;

  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    stage.current?.focus({ preventScroll: true });
  }, [step]);
  useLayoutEffect(() => {
    if (!error) return;
    const input = stage.current?.querySelector<HTMLElement>(
      `[data-draft-field="${error.field}"]`,
    );
    if (!input) return;
    const details = input.closest("details");
    if (details) details.open = true;
    input.focus({ preventScroll: true });
    input.scrollIntoView?.({ block: "center", behavior: "instant" });
  }, [error, step]);
  const patch = (value: Partial<Draft>) => {
    onChange({ ...draft, ...value });
    setError(null);
  };
  const weights = JSON.stringify(draft.weights);
  const payload = draftError(draft) ? null : runPayload(draft);
  const estimateKey = payload
    ? JSON.stringify([payload.scenario, payload.n, payload.concurrency])
    : "";
  const previewKey = JSON.stringify([draft.weights, draft.n]);
  const activePreview = preview?.requestKey === previewKey ? preview : null;
  const activeEstimate = estimate?.requestKey === estimateKey ? estimate : null;
  useEffect(() => {
    if (step !== 1 || !payload) {
      setEstimate(null);
      return;
    }
    const controller = new AbortController();
    setEstimate(null);
    let current = true;
    const timer = window.setTimeout(() => {
      api
        .request<Estimate>(
          "/estimate",
          "POST",
          {
            scenario: payload.scenario,
            n: payload.n,
            concurrency: payload.concurrency,
          },
          controller.signal,
        )
        .then((value) => {
          if (current) setEstimate({ ...value, requestKey: estimateKey });
        })
        .catch(() => {
          if (current) setEstimate(null);
        });
    }, 300);
    return () => {
      current = false;
      window.clearTimeout(timer);
      controller.abort();
    };
    // payload пересчитывается из draft; ключ фиксирует только значимые поля.
  }, [step, estimateKey]);
  useEffect(() => {
    if (step !== 1) return;
    const controller = new AbortController();
    let alive = true;
    setLoading(true);
    setPreviewError("");
    const timer = window.setTimeout(() => {
      api
        .request<Preview>(
          "/preview",
          "POST",
          { population: draft.weights, n: draft.n },
          controller.signal,
        )
        .then((p) => {
          if (alive) setPreview({ ...p, requestKey: previewKey });
        })
        .catch((e) => {
          if (alive && !ignored(e)) {
            setPreview(null);
            setPreviewError(message(e));
          }
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, 200);
    return () => {
      alive = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [step, draft.n, weights]);
  const next = () => {
    const problem = draftIssue(draft, true);
    if (problem) {
      setError(problem);
      setStep(problem.step);
      return;
    }
    setStep(1);
    setError(null);
  };
  const start = () => {
    const problem = draftIssue(draft);
    if (problem) {
      setError(problem);
      setStep(problem.step);
      return;
    }
    onRun();
  };
  const selected = Object.values(draft.weights).filter((n) => n > 0).length;
  return (
    <div className="composer">
      <Heading
        title="Новое исследование"
        description="Сравните предложения до запуска. Начните с вопроса, который хотите проверить."
      />
      <div className="stepper" aria-label="Этапы исследования">
        <button
          className={step === 0 ? "current" : "complete"}
          onClick={() => setStep(0)}
        >
          <span>{step === 1 ? <Check size={15} /> : 1}</span>Предложения
        </button>
        <i />
        <button className={step === 1 ? "current" : ""} onClick={next}>
          <span>2</span>Аудитория
        </button>
        <i />
        <span className="future-step">
          <b>3</b>Результат
        </span>
      </div>
      {(draftStatus || onReset) && (
        <div className="draft-status">
          {draftStatus && <span role="status">{draftStatus}</span>}
          {onReset && (
            <button
              className="text-link"
              onClick={() => {
                onReset();
                setError(null);
              }}
              disabled={busy}
            >
              Начать заново
            </button>
          )}
        </div>
      )}
      {draft.origin && (
        <div className="origin-note" role="status">
          {draft.origin.kind === "hypothesis" ? (
            <>
              <div>
                <strong>Проверка гипотезы «{draft.origin.lever}»</strong>
                <p>
                  Из исследования «{draft.origin.title}». A — текущий вариант{" "}
                  {draft.origin.variant} без изменений, B — новый текст:{" "}
                  {draft.origin.change?.toLowerCase()}. Текст B можно
                  отредактировать, аудитория уже ограничена затронутыми
                  сегментами.
                </p>
              </div>
              <Button
                kind="primary"
                onClick={next}
                disabled={busy || activeRun}
              >
                Проверить настройки A/B
                <ArrowRight size={17} />
              </Button>
            </>
          ) : (
            <div>
              <strong>Следующая итерация</strong>
              <p>
                Основа — исследование «{draft.origin.title}». Измените
                предложения или аудиторию: новый отчёт сохранит связь с исходным
                и сравнит их в один клик.
              </p>
            </div>
          )}
        </div>
      )}
      {step === 0 ? (
        <section
          className="composer-step"
          ref={stage}
          tabIndex={-1}
          aria-label="Предложения исследования"
        >
          <div className="research-intro">
            <label className="field">
              <span>Сценарий</span>
              <select
                value={draft.key}
                onChange={(e) => {
                  onTemplate(e.target.value);
                  setError(null);
                }}
              >
                {Object.keys(catalog.scenarios).map((key) => (
                  <option key={key} value={key}>
                    {TITLES[key] ?? catalog.scenarios[key].title}
                  </option>
                ))}
              </select>
            </label>
            <p>{catalog.scenarios[draft.key]?.description}</p>
          </div>
          <div className="question-fields">
            <label className="field">
              <span>Название исследования</span>
              <input
                {...fieldProps("title")}
                maxLength={200}
                value={draft.title}
                onChange={(e) => patch({ title: e.target.value })}
              />
              {fieldError("title")}
            </label>
            <label className="field">
              <span>Вопрос двойникам</span>
              <input
                {...fieldProps("question")}
                maxLength={1000}
                value={draft.question}
                onChange={(e) => patch({ question: e.target.value })}
              />
              {fieldError("question")}
            </label>
          </div>
          <div className="section-heading">
            <h2>Что сравниваем</h2>
            <label className="compact-field">
              Предложений{" "}
              <select
                aria-label="Количество предложений"
                value={draft.variantCount}
                onChange={(e) =>
                  patch({ variantCount: Number(e.target.value) })
                }
              >
                {[2, 3, 4, 5].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="offer-editor">
            {VARIANTS.slice(0, draft.variantCount).map((v, index) => (
              <label key={v} className={"offer-input variant-" + v}>
                <span>
                  <b>{v}</b>Предложение {v}
                </span>
                <textarea
                  {...fieldProps("variant-" + v)}
                  aria-label={"Предложение " + v}
                  maxLength={3000}
                  placeholder={
                    index === 0
                      ? "Опишите первое предложение…"
                      : "Чем отличается этот вариант?"
                  }
                  value={draft.variants[v] ?? ""}
                  onChange={(e) =>
                    patch({
                      variants: { ...draft.variants, [v]: e.target.value },
                    })
                  }
                />
                {fieldError("variant-" + v)}
              </label>
            ))}
          </div>
          <RespondentPreview draft={draft} />
          <details className="disclosure">
            <summary>
              <SlidersHorizontal size={16} />
              Контекст и причины отказа
            </summary>
            <div className="disclosure-content question-fields">
              <label className="field">
                <span>Контекст исследования</span>
                <textarea
                  maxLength={4000}
                  value={draft.description}
                  onChange={(e) => patch({ description: e.target.value })}
                />
              </label>
              <label className="field">
                <span>Категории отказа — одна на строку</span>
                <textarea
                  {...fieldProps("objections")}
                  maxLength={1500}
                  value={draft.objections.join("\n")}
                  onChange={(e) =>
                    patch({ objections: e.target.value.split("\n") })
                  }
                />
                {fieldError("objections")}
              </label>
            </div>
          </details>
          <div className="step-actions">
            <span>Для сравнения: {draft.variantCount}</span>
            <Button kind="primary" onClick={next}>
              Далее: аудитория
              <ArrowRight size={18} />
            </Button>
          </div>
        </section>
      ) : (
        <section
          className="composer-step"
          ref={stage}
          tabIndex={-1}
          aria-label="Аудитория исследования"
        >
          <div className="audience-intro">
            <div>
              <span className="mini-label">Размер исследования</span>
              <h2>
                <Users size={27} />
                {draft.n.toLocaleString("ru-RU")} <small>двойников</small>
              </h2>
              <p>Каждое предложение оценят одни и те же профили.</p>
            </div>
            <label className="field">
              <span>Размер аудитории</span>
              <select
                {...fieldProps("n")}
                value={draft.n}
                onChange={(e) => patch({ n: Number(e.target.value) })}
              >
                {[...new Set([50, 100, 200, 500, 1000, draft.n])]
                  .sort((a, b) => a - b)
                  .map((n) => (
                    <option key={n} value={n}>
                      {n.toLocaleString("ru-RU")}
                    </option>
                  ))}
              </select>
              {fieldError("n")}
            </label>
          </div>
          <div className="section-heading">
            <h2>Кого приглашаем</h2>
            <span>Сегментов: {selected} · относительные доли</span>
          </div>
          <p className="help">
            Нулевая доля исключает сегмент. Сумму нормирует движок; справа
            показано точное число профилей.
          </p>
          {fieldError("weights")}
          <div className="segment-editor">
            {Object.entries(catalog.segments).map(([sid, s]) => (
              <label
                key={sid}
                className={(draft.weights[sid] ?? 0) > 0 ? "active" : ""}
              >
                <span className="segment-avatar" aria-hidden="true">
                  {s.name[0]}
                </span>
                <span className="segment-name">
                  <strong>{s.name}</strong>
                  <small>
                    {s.region.slice(0, 2).join(", ")} · {s.age[0]}–{s.age[1]}{" "}
                    лет
                  </small>
                </span>
                <input
                  {...fieldProps("weights")}
                  aria-label={"Доля: " + s.name}
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={draft.weights[sid] ?? 0}
                  onChange={(e) =>
                    patch({
                      weights: {
                        ...draft.weights,
                        [sid]: Math.max(
                          0,
                          Math.min(100, Number(e.target.value)),
                        ),
                      },
                    })
                  }
                />
                <span className="segment-count">
                  {loading || !activePreview
                    ? "…"
                    : (activePreview.counts[sid] ?? 0)}
                  <small>профилей</small>
                </span>
              </label>
            ))}
          </div>
          <AudienceDistribution
            preview={
              !loading && !previewError
                ? (activePreview ?? undefined)
                : undefined
            }
            segments={catalog.segments}
            error={previewError}
          />
          {previewError && <Notice kind="error">{previewError}</Notice>}
          {!loading &&
            activePreview &&
            Object.entries(draft.weights).some(
              ([sid, w]) => w > 0 && !activePreview.counts[sid],
            ) && (
              <Notice>
                В одном из выбранных сегментов нет профилей после округления.
                Увеличьте его долю или аудиторию.
              </Notice>
            )}
          <details className="disclosure">
            <summary>
              <SlidersHorizontal size={16} />
              Модель и параметры запуска
            </summary>
            <div className="disclosure-content settings-grid">
              <label className="field">
                <span>Режим</span>
                <select
                  value={draft.mock ? "demo" : "llm"}
                  disabled={demo}
                  onChange={(e) => patch({ mock: e.target.value === "demo" })}
                >
                  <option value="demo">Демо без внешних запросов</option>
                  <option value="llm">Подключённая LLM</option>
                </select>
              </label>
              <label className="field">
                <span>Seed популяции и демо</span>
                <input
                  type="number"
                  min={0}
                  max={999999}
                  {...fieldProps("seed")}
                  value={draft.seed}
                  onChange={(e) => patch({ seed: Number(e.target.value) })}
                />
                {fieldError("seed")}
              </label>
              <label className="field">
                <span>Параллельных запросов LLM</span>
                <input
                  type="number"
                  min={1}
                  max={64}
                  {...fieldProps("concurrency")}
                  value={draft.concurrency}
                  onChange={(e) =>
                    patch({ concurrency: Number(e.target.value) })
                  }
                />
                {fieldError("concurrency")}
              </label>
              <p className="help">
                {draft.mock
                  ? "Демо использует правила и ключевые слова. Проценты показывают рабочий процесс."
                  : "Профили и тексты предложений передаются в модель, настроенную администратором сервера."}
              </p>
            </div>
          </details>
          <LaunchReview
            draft={draft}
            catalog={catalog}
            counts={
              !loading && !previewError ? activePreview?.counts : undefined
            }
            onEdit={() => setStep(0)}
          />
          {!activeEstimate && (
            <p className="help" role="status">
              {draft.mock
                ? "Демо выполняется без запросов к модели."
                : "Оценка нагрузки пока недоступна. Фактические расходы зависят от настроенной модели."}
            </p>
          )}
          {activeEstimate && (
            <div className="run-estimate" aria-live="polite">
              <span className="mini-label">
                {draft.mock
                  ? "Демо без запросов · с подключённой LLM было бы"
                  : "Оценка запуска на LLM"}
              </span>
              <div>
                <span>
                  <strong>
                    {activeEstimate.requests.toLocaleString("ru-RU")}
                  </strong>{" "}
                  запросов
                </span>
                <span>
                  <strong>
                    ≈{" "}
                    {decimal(
                      (activeEstimate.input_tokens +
                        activeEstimate.output_tokens) /
                        1000,
                      0,
                    )}{" "}
                    тыс.
                  </strong>{" "}
                  токенов
                </span>
                <span>
                  <strong>
                    ≈{" "}
                    {activeEstimate.minutes < 1
                      ? "< 1"
                      : decimal(Math.ceil(activeEstimate.minutes), 0)}{" "}
                    мин
                  </strong>
                </span>
                {activeEstimate.cost !== null && (
                  <span>
                    <strong>
                      ≈ {decimal(activeEstimate.cost, 0)}{" "}
                      {activeEstimate.currency}
                    </strong>
                  </span>
                )}
              </div>
              <p className="help">
                {activeEstimate.detail} Включая один запрос простого подхода для
                сравнения.{" "}
                {activeEstimate.cost === null
                  ? "Стоимость не рассчитана: тариф модели не задан."
                  : "Это предварительная оценка, фактические расходы могут отличаться."}
              </p>
            </div>
          )}
          <div className="step-actions">
            <Button onClick={() => setStep(0)}>
              <ArrowLeft size={17} />
              Предложения
            </Button>
            <div>
              <span>
                {(draft.n * draft.variantCount).toLocaleString("ru-RU")} оценок
                {draft.mock ? " · демо" : ""}
              </span>
              <Button
                kind="primary"
                disabled={
                  busy ||
                  (!activeRun &&
                    !draftError(draft) &&
                    (loading || !!previewError))
                }
                onClick={activeRun ? onRun : start}
              >
                {busy
                  ? "Запускаем…"
                  : activeRun
                    ? "К текущему запуску"
                    : "Запустить исследование"}
                <ArrowRight size={18} />
              </Button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
