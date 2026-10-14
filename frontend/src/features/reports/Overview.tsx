import { Notice, percent } from "../../components";
import { COLORS, type Catalog, type Experiment } from "../../types";
import type { Insights } from "./types";
import ConversionChart from "./ConversionChart";
import SnapshotDetails from "./SnapshotDetails";
export default function Overview({
  record,
  catalog,
  focus,
  segment,
  setSegment,
  variant,
  setVariant,
}: {
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
                  ? "Вариант " + candidate
                  : "Равный результат"}
              </h2>
              <p>
                {leaders.length === 1
                  ? percent(focus.summary.best) +
                    " согласий в выбранной аудитории"
                  : "Варианты " +
                    leaders.join(", ") +
                    " получили одинаковую долю согласий."}
              </p>
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
              )}
              <p className="help">
                {segment !== "all"
                  ? "Реплика — синтетический пример, а не полное распределение причин. "
                  : ""}
                Проверьте причины решений в интервью на живой аудитории.
              </p>
            </>
          )}
        </aside>
      </div>
      {segment === "all" ? (
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
            {Object.entries(record.report[variant].objections)
              .sort((a, b) => b[1] - a[1])
              .map(([name, n]) => (
                <div key={name}>
                  <span>{name}</span>
                  <div>
                    <i
                      style={{
                        width:
                          (n /
                            Math.max(
                              1,
                              ...Object.values(
                                record.report[variant].objections,
                              ),
                            )) *
                            100 +
                          "%",
                      }}
                    />
                  </div>
                  <b>{n}</b>
                </div>
              ))}
          </div>
          <p className="help">
            Количество ответов по всей аудитории для предложения {variant}.
          </p>
        </>
      ) : (
        <Notice>
          Количество причин отказа сохранено только по всей аудитории. Для
          сегмента смотрите примеры во вкладке «Голоса».
        </Notice>
      )}
      <SnapshotDetails record={record} />
    </>
  );
}
