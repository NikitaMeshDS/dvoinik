import { ArrowRight } from "lucide-react";
import { Notice, decimal, percent } from "../../components";
import { COLORS, type Catalog, type Experiment } from "../../types";
import type { BaselineAgreement, Insights, LivePlan } from "./types";
import ConversionChart from "./ConversionChart";
import SnapshotDetails from "./SnapshotDetails";
import BaselineCard from "./BaselineCard";
export default function Overview({
  record,
  catalog,
  focus,
  segment,
  setSegment,
  variant,
  setVariant,
  baseline,
  plan,
  onPlan,
  hypothesisCount,
  onHypotheses,
}: {
  hypothesisCount?: number;
  onHypotheses?: () => void;
  baseline?: BaselineAgreement | null;
  plan?: LivePlan;
  onPlan?: () => void;
  record: Experiment;
  catalog: Catalog;
  focus: Insights | null;
  segment: string;
  setSegment: (s: string) => void;
  variant: string;
  setVariant: (s: string) => void;
}) {
  const variants = Object.keys(record.report),
    segments = Object.keys(record.scenario.population);
  const hasSegmentReasons =
    segment !== "all" &&
    record.report[variant]?.segments[segment]?.objections !== undefined;
  const reasons: Record<string, number> =
    segment === "all"
      ? record.report[variant].objections
      : (record.report[variant]?.segments[segment]?.objections ?? {});
  const leaders = focus?.summary.leaders ?? [],
    candidate = leaders[0],
    candidateResult = candidate ? focus?.report[candidate] : undefined,
    quote = candidateResult?.quotes[0];
  return (
    <>
      <div className="section-heading">
        <h2>Результаты по сегментам</h2>
        <span>Готовность подключить предложение</span>
      </div>
      <div
        className="matrix-scroll"
        tabIndex={0}
        role="region"
        aria-label="Матрица результатов с горизонтальной прокруткой"
      >
        <table className="matrix">
          <thead>
            <tr>
              <th scope="col">Аудитория</th>
              {variants.map((v, i) => (
                <th scope="col" key={v}>
                  <span
                    className="variant-letter"
                    style={{
                      color: COLORS[i],
                      background: COLORS[i] + "14",
                    }}
                  >
                    {v}
                  </span>
                  Предложение {v}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {segments.map((sid) => {
              const rates = variants.map((v) => {
                const cell = record.report[v].segments[sid];
                return cell?.n ? cell.yes / cell.n : null;
              });
              const best = rates.some((r) => r !== null)
                ? Math.max(...rates.filter((r): r is number => r !== null))
                : null;
              return (
                <tr key={sid} className={segment === sid ? "selected" : ""}>
                  <th scope="row">
                    <button
                      onClick={() => setSegment(sid)}
                      aria-pressed={segment === sid}
                    >
                      {catalog.segments[sid]?.name ?? sid}
                    </button>
                  </th>
                  {variants.map((v, i) => {
                    const c = record.report[v].segments[sid],
                      rate = rates[i],
                      leading = rate !== null && rate === best;
                    return (
                      <td key={v} className={leading ? "leading" : ""}>
                        <strong>{percent(rate)}</strong>
                        <small>
                          {c?.n ?? 0} / {record.population_counts[sid] ?? 0}{" "}
                          ответов
                        </small>
                        <span className="matrix-track">
                          <i
                            style={{
                              width: (rate ?? 0) * 100 + "%",
                              background: COLORS[i],
                            }}
                          />
                        </span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="help">
        Нажмите название сегмента для разбора. «—» означает отсутствие ответов.
        Выделены наибольшие доли в строке; статистическая значимость не
        проверялась.
      </p>
      <label className="audience-filter field">
        <span>Разобрать аудиторию</span>
        <select value={segment} onChange={(e) => setSegment(e.target.value)}>
          <option value="all">Вся аудитория</option>
          {segments.map((sid) => (
            <option key={sid} value={sid}>
              {catalog.segments[sid]?.name ?? sid}
            </option>
          ))}
        </select>
      </label>
      <div className="analysis-grid" aria-busy={!focus}>
        <section className="analysis-chart">
          <div className="section-heading">
            <h2>Готовность подключить</h2>
            <span>
              {segment === "all"
                ? record.n
                : (record.population_counts[segment] ?? 0)}{" "}
              профилей на предложение
            </span>
          </div>
          {focus ? (
            <ConversionChart report={focus.report} />
          ) : (
            <p className="help">Готовим разбор…</p>
          )}
          <p className="help">
            Линии — 95% интервалы ответов симуляции. Они не измеряют точность
            прогноза реального спроса.
          </p>
        </section>
        <aside className="next-step">
          <span className="mini-label">Что проверить дальше</span>
          {!focus ? (
            <p>Готовим разбор…</p>
          ) : !candidate ? (
            <p>
              Нет валидных ответов. Проверьте покрытие и подключение модели.
            </p>
          ) : (
            <>
              <h2>
                {leaders.length === 1
                  ? "Гипотеза: вариант " + candidate
                  : "Равный результат"}
              </h2>
              <p>
                {leaders.length === 1
                  ? "Лидер симуляции — " +
                    percent(focus.summary.best) +
                    " согласий в выбранной аудитории. Это повод проверить вариант на людях, а не вывод о спросе."
                  : "Варианты " +
                    leaders.join(", ") +
                    " получили одинаковую долю согласий."}
              </p>
              {focus.stability && leaders.length === 1 && (
                <p
                  className={"stability-line " + focus.stability.level}
                  title={focus.stability.detail}
                >
                  {focus.stability.label}: {focus.stability.leader} впереди{" "}
                  {focus.stability.runner_up} в{" "}
                  {decimal(focus.stability.share * 100, 0)}% повторных выборок
                </p>
              )}
              {segment !== "all" ? (
                quote ? (
                  <blockquote>
                    <span>
                      {quote.decision ? "Готовы подключить" : "Отказались"}
                    </span>
                    <p>«{quote.quote}»</p>
                    <cite>{quote.who}</cite>
                  </blockquote>
                ) : (
                  <p className="help">
                    В подборке нет объяснений этого сегмента для выбранного
                    варианта.
                  </p>
                )
              ) : (
                <>
                  <p className="barrier">
                    {candidateResult &&
                    Object.keys(candidateResult.objections).length
                      ? "Основной барьер: " +
                        Object.entries(candidateResult.objections).sort(
                          (a, b) => b[1] - a[1],
                        )[0][0] +
                        "."
                      : "В сохранённых ответах нет причин отказа."}
                  </p>
                  {plan?.comparisons[0] && (
                    <p className="plan-hint">
                      Чтобы различить {plan.comparisons[0].pair.join(" и ")}{" "}
                      опросом, нужно{" "}
                      {plan.comparisons[0].n_per_variant === null
                        ? "больше, чем разумная выборка: разница меньше 2 п.п."
                        : "≈ " +
                          plan.comparisons[0].n_per_variant.toLocaleString(
                            "ru-RU",
                          ) +
                          " оценок на каждое предложение."}
                    </p>
                  )}
                </>
              )}
              {onPlan && segment === "all" ? (
                <div className="next-links">
                  {onHypotheses && hypothesisCount ? (
                    <button
                      className="text-link with-icon"
                      onClick={onHypotheses}
                    >
                      {hypothesisCount === 1
                        ? "1 гипотеза"
                        : hypothesisCount + " гипотезы"}
                      , что поменять в предложении
                      <ArrowRight size={15} aria-hidden="true" />
                    </button>
                  ) : null}
                  <button className="text-link with-icon" onClick={onPlan}>
                    План живой проверки и вопросы для интервью
                    <ArrowRight size={15} aria-hidden="true" />
                  </button>
                </div>
              ) : (
                <p className="help">
                  Реплика — синтетический пример, а не полное распределение
                  причин. Проверьте причины решений в интервью на живой
                  аудитории.
                </p>
              )}
            </>
          )}
        </aside>
      </div>
      {segment === "all" && (
        <BaselineCard record={record} baseline={baseline} />
      )}
      {segment === "all" || hasSegmentReasons ? (
        <>
          <div className="section-heading">
            <h2>Причины отказа</h2>
            <label className="compact-field">
              Предложение{" "}
              <select
                aria-label="Предложение для причин отказа"
                value={variant}
                onChange={(e) => setVariant(e.target.value)}
              >
                {variants.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="objections">
            {Object.entries(reasons)
              .sort((a, b) => b[1] - a[1])
              .map(([name, n]) => (
                <div key={name}>
                  <span>{name}</span>
                  <div>
                    <i
                      style={{
                        width:
                          (n / Math.max(1, ...Object.values(reasons))) * 100 +
                          "%",
                      }}
                    />
                  </div>
                  <b>{n}</b>
                </div>
              ))}
          </div>
          <p className="help">
            {Object.keys(reasons).length
              ? "Количество ответов «нет» " +
                (segment === "all"
                  ? "по всей аудитории"
                  : "в сегменте «" +
                    (catalog.segments[segment]?.name ?? segment) +
                    "»") +
                " для предложения " +
                variant +
                "."
              : "Для предложения " +
                variant +
                " нет отказов в выбранной аудитории."}
          </p>
        </>
      ) : (
        <Notice>
          Снимок создан до сохранения причин по сегментам: количество причин
          доступно только по всей аудитории. Для сегмента смотрите примеры во
          вкладке «Голоса».
        </Notice>
      )}
      <SnapshotDetails record={record} />
    </>
  );
}
