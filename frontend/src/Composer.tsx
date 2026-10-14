import { useEffect, useState } from "react";
import {
  ArrowRight,
  ArrowLeft,
  Users,
  Check,
  SlidersHorizontal,
} from "lucide-react";
import { api, ignored, message } from "./api";
import { draftError } from "./draft";
import { Button, Heading, Notice } from "./components";
import { VARIANTS, TITLES, type Catalog, type Draft } from "./types";
type Preview = {
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
}: {
  catalog: Catalog;
  draft: Draft;
  onChange: (d: Draft) => void;
  onTemplate: (key: string) => void;
  onRun: () => void;
  demo: boolean;
  busy: boolean;
  activeRun?: boolean;
}) {
  const [step, setStep] = useState(0),
    [error, setError] = useState(""),
    [preview, setPreview] = useState<Preview | null>(null),
    [previewError, setPreviewError] = useState(""),
    [loading, setLoading] = useState(false);
  const patch = (value: Partial<Draft>) => {
    onChange({ ...draft, ...value });
    setError("");
  };
  const weights = JSON.stringify(draft.weights);
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
          if (alive) setPreview(p);
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
    const problem = draftError({ ...draft, weights: { audience: 1 } });
    if (problem) {
      setError(problem);
      return;
    }
    setStep(1);
    setError("");
  };
  const start = () => {
    const problem = draftError(draft);
    if (problem) {
      setError(problem);
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
      {error && <Notice kind="error">{error}</Notice>}
      {step === 0 ? (
        <section className="composer-step">
          <div className="research-intro">
            <label className="field">
              <span>Сценарий</span>
              <select
                value={draft.key}
                onChange={(e) => {
                  onTemplate(e.target.value);
                  setError("");
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
                maxLength={200}
                value={draft.title}
                onChange={(e) => patch({ title: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Вопрос двойникам</span>
              <input
                maxLength={1000}
                value={draft.question}
                onChange={(e) => patch({ question: e.target.value })}
              />
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
              </label>
            ))}
          </div>
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
                  maxLength={1500}
                  value={draft.objections.join("\n")}
                  onChange={(e) =>
                    patch({ objections: e.target.value.split("\n") })
                  }
                />
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
        <section className="composer-step">
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
                  {loading ? "…" : (preview?.counts[sid] ?? 0)}
                  <small>профилей</small>
                </span>
              </label>
            ))}
          </div>
          {previewError && <Notice kind="error">{previewError}</Notice>}
          {!loading &&
            preview &&
            Object.entries(draft.weights).some(
              ([sid, w]) => w > 0 && !preview.counts[sid],
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
                  value={draft.seed}
                  onChange={(e) => patch({ seed: Number(e.target.value) })}
                />
              </label>
              <label className="field">
                <span>Параллельных запросов LLM</span>
                <input
                  type="number"
                  min={1}
                  max={64}
                  value={draft.concurrency}
                  onChange={(e) =>
                    patch({ concurrency: Number(e.target.value) })
                  }
                />
              </label>
              <p className="help">
                {draft.mock
                  ? "Демо использует правила и ключевые слова. Проценты показывают рабочий процесс."
                  : "Профили и тексты предложений передаются в модель, настроенную администратором сервера."}
              </p>
            </div>
          </details>
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
                disabled={busy || (!activeRun && (loading || !!previewError))}
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
