import { useEffect, useState } from "react";
import {
  ArrowRight,
  Download,
  GitCompare,
  FileJson,
  FileSpreadsheet,
  Users,
  MessageSquare,
  ClipboardCheck,
  BarChart3,
  RefreshCw,
} from "lucide-react";
import { api, download, ignored, message } from "./api";
import {
  Back,
  Button,
  Heading,
  Menu,
  Notice,
  date,
  percent,
} from "./components";
import {
  COLORS,
  type Catalog,
  type Experiment,
  type ReportItem,
  type Validation,
  type ValidationResult,
} from "./types";
type Insights = {
  report: Record<string, ReportItem>;
  summary: {
    leaders: string[];
    gap_pp: number;
    best: number;
    failed_n: number;
  };
  quality: { kind: string; title: string; detail: string };
};
type ExportKind = "record" | "validation" | "survey-template" | "preview";
export default function Report({
  record,
  catalog,
  onBack,
  onReuse,
  onUpdated,
  onCompare,
  onError,
  pending,
  onRetry,
}: {
  record: Experiment;
  catalog: Catalog;
  onBack: () => void;
  onReuse: () => void;
  onUpdated: (r: Experiment) => void;
  onCompare: () => void;
  onError: (e: unknown) => void;
  pending?: string;
  onRetry?: () => void;
}) {
  const [tab, setTab] = useState("overview"),
    [segment, setSegment] = useState("all"),
    [base, setBase] = useState<Insights | null>(null),
    [focus, setFocus] = useState<Insights | null>(null),
    [variant, setVariant] = useState(Object.keys(record.report)[0]),
    [decision, setDecision] = useState("all");
  const exportFile = (format: "json" | "csv", kind: ExportKind = "record") =>
    download("/export", { record_id: record.id, format, kind }).catch(onError);
  useEffect(() => {
    let alive = true;
    setBase(null);
    api
      .request<Insights>("/insights", "POST", {
        record_id: record.id,
        segment: "all",
      })
      .then((value) => {
        if (alive) setBase(value);
      })
      .catch((e) => {
        if (alive && !ignored(e)) onError(e);
      });
    return () => {
      alive = false;
    };
  }, [record]);
  useEffect(() => {
    let alive = true;
    setFocus(null);
    if (segment === "all") {
      setFocus(base);
      return;
    }
    api
      .request<Insights>("/insights", "POST", { record_id: record.id, segment })
      .then((value) => {
        if (alive) setFocus(value);
      })
      .catch((e) => {
        if (alive && !ignored(e)) onError(e);
      });
    return () => {
      alive = false;
    };
  }, [segment, base, record.id]);
  const variants = Object.keys(record.report),
    segments = Object.keys(record.scenario.population),
    summary = base?.summary;
  const leaders = focus?.summary.leaders ?? [],
    candidate = leaders[0],
    candidateResult = candidate ? focus?.report[candidate] : undefined;
  const quote = candidateResult?.quotes[0];
  const quotes = (record.report[variant]?.quotes ?? []).filter(
    (q) =>
      (segment === "all" || q.segment_id === segment) &&
      (decision === "all" || Boolean(q.decision) === (decision === "yes")),
  );
  return (
    <>
      <Back onClick={onBack} />
      <Heading
        title={record.scenario.title}
        description={
          (record.sample
            ? "Демонстрационный пример"
            : date(record.created_at)) +
          " · " +
          record.model
        }
        action={
          <div className="heading-actions">
            <Button kind="primary" onClick={onReuse}>
              Следующая итерация
              <ArrowRight size={18} />
            </Button>
            <Menu label="Действия с отчётом">
              <button onClick={() => exportFile("json")}>
                <FileJson size={17} />
                Отчёт JSON
              </button>
              <button onClick={() => exportFile("csv")}>
                <FileSpreadsheet size={17} />
                Сегменты CSV
              </button>
              <button onClick={onCompare}>
                <GitCompare size={17} />
                Сравнить с исследованием
              </button>
            </Menu>
          </div>
        }
      />
      {pending && (
        <Notice kind="error">
          <strong>Результат пока не записан в архив.</strong> {pending}
          <div className="inline-actions">
            {onRetry && (
              <Button onClick={onRetry}>
                <RefreshCw size={15} />
                Повторить сохранение
              </Button>
            )}
            <button className="text-link" onClick={() => exportFile("json")}>
              Скачать полный JSON
            </button>
          </div>
        </Notice>
      )}
      {base && (
        <div className={"quality-note " + base.quality.kind}>
          <span />
          <div>
            <strong>{base.quality.title}</strong>
            <p>{base.quality.detail}</p>
          </div>
        </div>
      )}
      <div className="report-summary">
        <div className="summary-main">
          <span>
            {summary?.leaders.length === 1
              ? "Лидер симуляции"
              : summary?.leaders.length
                ? "Равный результат"
                : "Доля согласий"}
          </span>
          <strong>
            {summary?.leaders.length ? percent(summary.best, 0) : "—"}
          </strong>
          <small>
            {summary?.leaders.length
              ? "Вариант " + summary.leaders.join(" / ")
              : "Нет валидных ответов"}{" "}
            · вся аудитория
          </small>
        </div>
        <div>
          <span>Двойников</span>
          <strong>{record.n.toLocaleString("ru-RU")}</strong>
          <small>Сегментов: {segments.length}</small>
        </div>
        <div>
          <span>Предложений</span>
          <strong>{variants.length}</strong>
          <small>
            {Object.values(record.report)
              .reduce((n, r) => n + r.n, 0)
              .toLocaleString("ru-RU")}{" "}
            валидных ответов
          </small>
        </div>
        <div>
          <span>Отрыв от следующего</span>
          <strong>
            {summary ? summary.gap_pp.toFixed(1) : "—"} <small>п.п.</small>
          </strong>
          <small>Описательное сравнение</small>
        </div>
      </div>
      {!!base?.summary.failed_n && (
        <details className="disclosure error-details">
          <summary>
            {base.summary.failed_n} ошибок модели · проверить покрытие
          </summary>
          <div className="disclosure-content">
            {Object.entries(record.report).map(([vid, r]) => (
              <p key={vid}>
                Вариант {vid}: {r.n} / {r.requested_n} ответов.{" "}
                {(r.failure_examples ?? []).join(" ")}
              </p>
            ))}
          </div>
        </details>
      )}
      <div
        className="report-tabs"
        role="tablist"
        aria-label="Содержание отчёта"
      >
        {[
          ["overview", "Результат", BarChart3],
          ["people", "Аудитория", Users],
          ["voices", "Голоса", MessageSquare],
          ["validation", "Проверка опросом", ClipboardCheck],
        ].map(([id, label, Icon]) => {
          const I = Icon as typeof BarChart3;
          return (
            <button
              key={id as string}
              id={"tab-" + id}
              role="tab"
              aria-selected={tab === id}
              aria-controls={"panel-" + id}
              tabIndex={tab === id ? 0 : -1}
              onKeyDown={(e) => {
                const ids = ["overview", "people", "voices", "validation"];
                const index = ids.indexOf(tab);
                const next =
                  e.key === "ArrowRight"
                    ? (index + 1) % 4
                    : e.key === "ArrowLeft"
                      ? (index + 3) % 4
                      : e.key === "Home"
                        ? 0
                        : e.key === "End"
                          ? 3
                          : null;
                if (next !== null) {
                  e.preventDefault();
                  setTab(ids[next]);
                  document.getElementById("tab-" + ids[next])?.focus();
                }
              }}
              onClick={() => setTab(id as string)}
            >
              <I size={16} />
              {label as string}
            </button>
          );
        })}
      </div>
      <section
        role="tabpanel"
        id={"panel-" + tab}
        aria-labelledby={"tab-" + tab}
      >
        {tab === "overview" && (
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
                      ? Math.max(
                          ...rates.filter((r): r is number => r !== null),
                        )
                      : null;
                    return (
                      <tr
                        key={sid}
                        className={segment === sid ? "selected" : ""}
                      >
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
                                {c?.n ?? 0} /{" "}
                                {record.population_counts[sid] ?? 0} ответов
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
              Нажмите название сегмента для разбора. «—» означает отсутствие
              ответов. Выделены наибольшие доли в строке; статистическая
              значимость не проверялась.
            </p>
            <label className="audience-filter field">
              <span>Разобрать аудиторию</span>
              <select
                value={segment}
                onChange={(e) => setSegment(e.target.value)}
              >
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
                  Линии — 95% интервалы ответов симуляции. Они не измеряют
                  точность прогноза реального спроса.
                </p>
              </section>
              <aside className="next-step">
                <span className="mini-label">Что проверить дальше</span>
                {!focus ? (
                  <p>Готовим разбор…</p>
                ) : !candidate ? (
                  <p>
                    Нет валидных ответов. Проверьте покрытие и подключение
                    модели.
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
                            {quote.decision
                              ? "Готовы подключить"
                              : "Отказались"}
                          </span>
                          <p>«{quote.quote}»</p>
                          <cite>{quote.who}</cite>
                        </blockquote>
                      ) : (
                        <p className="help">
                          В подборке нет объяснений этого сегмента для
                          выбранного варианта.
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
                  Количество ответов по всей аудитории для предложения {variant}
                  .
                </p>
              </>
            ) : (
              <Notice>
                Количество причин отказа сохранено только по всей аудитории. Для
                сегмента смотрите примеры во вкладке «Голоса».
              </Notice>
            )}
            <details className="disclosure">
              <summary>Предложения и настройки сохранённого снимка</summary>
              <div className="disclosure-content">
                <p>
                  <strong>Вопрос:</strong> {record.scenario.question}
                </p>
                <p>{record.scenario.description}</p>
                <div className="saved-offers">
                  {Object.entries(record.scenario.variants).map(([v, text]) => (
                    <div key={v} className={"variant-" + v}>
                      <b>Предложение {v}</b>
                      <p>{text}</p>
                    </div>
                  ))}
                </div>
                <p className="help">
                  Seed {record.seed} · {record.model} · {record.elapsed_seconds}{" "}
                  с · ID {record.id}
                </p>
              </div>
            </details>
          </>
        )}
        {tab === "people" && (
          <>
            <div className="section-heading">
              <h2>Профили аудитории</h2>
              <span>Один пример на сегмент</span>
            </div>
            <p className="help">
              Синтетические характеристики основаны на экспертных
              предположениях. Калибровка ещё не подтверждена.
            </p>
            <div className="profile-grid">
              {record.population_sample.map((p) => (
                <article className="profile" key={p.segment}>
                  <div>
                    <span className="profile-avatar">{p.name[0]}</span>
                    <div>
                      <h3>
                        {p.name}, {p.age}
                      </h3>
                      <small>{p.region}</small>
                    </div>
                    <span className="profile-count">
                      {record.population_counts[p.segment]}
                      <small>профилей</small>
                    </span>
                  </div>
                  <h4>{catalog.segments[p.segment]?.name ?? p.segment}</h4>
                  <p>{p.income}</p>
                  <div className="habit-tags">
                    {p.habits.map((h) => (
                      <span key={h}>{h}</span>
                    ))}
                  </div>
                  <p className="help">{p.attitude}</p>
                </article>
              ))}
            </div>
          </>
        )}
        {tab === "voices" && (
          <>
            <div className="section-heading">
              <h2>Голоса двойников</h2>
              <span>Сохранённая подборка объяснений</span>
            </div>
            <div className="filter-bar">
              <select
                aria-label="Предложение для голосов"
                value={variant}
                onChange={(e) => setVariant(e.target.value)}
              >
                {variants.map((v) => (
                  <option key={v} value={v}>
                    Предложение {v}
                  </option>
                ))}
              </select>
              <select
                aria-label="Сегмент голосов"
                value={segment}
                onChange={(e) => setSegment(e.target.value)}
              >
                <option value="all">Все сегменты</option>
                {segments.map((s) => (
                  <option key={s} value={s}>
                    {catalog.segments[s]?.name ?? s}
                  </option>
                ))}
              </select>
              <select
                aria-label="Решение двойников"
                value={decision}
                onChange={(e) => setDecision(e.target.value)}
              >
                <option value="all">Все решения</option>
                <option value="yes">Готовы подключить</option>
                <option value="no">Отказались</option>
              </select>
            </div>
            <div className="voice-grid">
              {quotes.length ? (
                quotes.map((q, i) => (
                  <blockquote key={i} className="voice">
                    <span className={q.decision ? "yes" : "no"}>
                      {q.decision ? "Готовы подключить" : "Отказались"}
                    </span>
                    <p>«{q.quote}»</p>
                    <cite>
                      {q.who}
                      <small>{q.segment}</small>
                    </cite>
                  </blockquote>
                ))
              ) : (
                <Notice>
                  В сохранённой подборке нет таких ответов. Попробуйте другой
                  фильтр.
                </Notice>
              )}
            </div>
            <p className="help">
              Это синтетические объяснения. Подборка не представляет все ответы
              аудитории.
            </p>
          </>
        )}
        <div hidden={tab !== "validation"}>
          <ValidationPanel
            record={record}
            onUpdated={onUpdated}
            onExport={exportFile}
            onError={onError}
          />
        </div>
      </section>
    </>
  );
}
function ConversionChart({ report }: { report: Record<string, ReportItem> }) {
  const rows = Object.entries(report);
  if (!rows.some(([, r]) => r.n))
    return (
      <Notice kind="error">
        Нет валидных ответов для выбранной аудитории.
      </Notice>
    );
  const width = 640,
    height = rows.length * 64 + 34,
    start = 94,
    scale = 455;
  return (
    <svg
      className="conversion-chart"
      viewBox={"0 0 " + width + " " + height}
      role="img"
      aria-label="Доля согласий и 95-процентные интервалы симуляции"
    >
      <title>
        {rows
          .map(
            ([v, r]) =>
              "Вариант " + v + ": " + percent(r.n ? r.conversion : null),
          )
          .join("; ")}
      </title>
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line
            x1={start + t * scale}
            x2={start + t * scale}
            y1={4}
            y2={height - 28}
            className="chart-grid"
          />
          <text
            x={start + t * scale}
            y={height - 7}
            textAnchor="middle"
            className="axis-label"
          >
            {t * 100}%
          </text>
        </g>
      ))}
      {rows.map(([v, r], i) => {
        const y = i * 64 + 25,
          rate = r.n ? r.conversion : null;
        return (
          <g key={v}>
            <text x={0} y={y + 5} className="chart-label">
              Вариант {v}
            </text>
            {rate !== null ? (
              <>
                <rect
                  x={start}
                  y={y - 16}
                  width={Math.max(1, rate * scale)}
                  height={32}
                  rx={5}
                  fill={COLORS[i]}
                />
                <line
                  x1={start + r.confidence_interval[0] * scale}
                  x2={start + r.confidence_interval[1] * scale}
                  y1={y}
                  y2={y}
                  className="interval"
                />
                <text
                  x={Math.min(
                    width - 48,
                    start + r.confidence_interval[1] * scale + 9,
                  )}
                  y={y + 5}
                  className="chart-value"
                >
                  {percent(rate, 0)}
                </text>
              </>
            ) : (
              <text x={start} y={y + 5} className="axis-label">
                Нет ответов
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
function ValidationMetrics({ result }: { result: ValidationResult }) {
  return (
    <>
      <div className="validation-metrics">
        <div>
          <span>Ошибка долей</span>
          <strong>
            {(result.mae_conversion * 100).toFixed(1)} <small>п.п.</small>
          </strong>
        </div>
        <div>
          <span>Корреляция рангов</span>
          <strong>
            {result.spearman_variants === null
              ? "—"
              : result.spearman_variants.toFixed(2)}
          </strong>
        </div>
        <div>
          <span>Совпадение лидера</span>
          <strong>
            {result.winner_match === null
              ? "Не определено"
              : result.winner_match
                ? "Да"
                : "Нет"}
          </strong>
        </div>
      </div>
      <p className="help">
        {result.survey_n} ответов опроса · {result.matched_cells} пар «вариант —
        сегмент». Подлинность опроса приложение не проверяет.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Вариант</th>
              <th>Сегмент</th>
              <th>Ответов</th>
              <th>Опрос</th>
              <th>Симуляция</th>
              <th>Ошибка</th>
            </tr>
          </thead>
          <tbody>
            {result.cells.map((c) => (
              <tr key={c.variant + c.segment}>
                <td>{c.variant}</td>
                <td>{c.segment}</td>
                <td>{c.survey_n}</td>
                <td>{percent(c.actual)}</td>
                <td>{percent(c.predicted)}</td>
                <td>{percent(c.error)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
function ValidationPanel({
  record,
  onUpdated,
  onExport,
  onError,
}: {
  record: Experiment;
  onUpdated: (r: Experiment) => void;
  onExport: (format: "json" | "csv", kind: ExportKind) => void;
  onError: (e: unknown) => void;
}) {
  const [csv, setCsv] = useState(""),
    [filename, setFilename] = useState(""),
    [preview, setPreview] = useState<{
      record: Experiment;
      base_validation: Validation | null;
    } | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const inspect = async (content: string) => {
    setBusy(true);
    setError("");
    try {
      setPreview(
        await api.request(
          "/experiments/" + record.id + "/validation/preview",
          "POST",
          { csv: content },
        ),
      );
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.request<Experiment>(
        "/experiments/" + record.id + "/validation",
        "PUT",
        { csv, base_validation: preview.base_validation },
      );
      onUpdated(result);
      setPreview(null);
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <div className="section-heading">
        <h2>Сопоставьте ответы с живым опросом</h2>
        <Menu label="Файлы проверки">
          <button onClick={() => onExport("csv", "survey-template")}>
            <Download size={17} />
            Шаблон CSV
          </button>
          {record.validation && (
            <button onClick={() => onExport("json", "validation")}>
              <FileJson size={17} />
              Метрики JSON
            </button>
          )}
          {preview && (
            <button onClick={() => onExport("json", "preview")}>
              <FileJson size={17} />
              Предпросмотр JSON
            </button>
          )}
        </Menu>
      </div>
      <p className="help">
        CSV: segment, variant, decision. Одна оценка предложения на строку;
        decision — 0 или 1. Нули в шаблоне замените настоящими ответами.
      </p>
      <label className="upload-area">
        <ClipboardCheck size={24} />
        <strong>{filename || "Выберите CSV опроса"}</strong>
        <span>UTF-8 · до 5 МБ</span>
        <input
          type="file"
          accept=".csv,text/csv"
          aria-label="CSV живого опроса"
          disabled={busy}
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setPreview(null);
            setError("");
            if (file.size > 5 * 1024 * 1024) {
              setError("Максимальный размер CSV — 5 МБ.");
              return;
            }
            const content = await file.text();
            setCsv(content);
            setFilename(file.name);
            await inspect(content);
          }}
        />
      </label>
      {busy && (
        <p className="help" role="status">
          Сопоставляем ответы…
        </p>
      )}
      {error && (
        <Notice kind="error">
          {error}
          {preview && (
            <div className="inline-actions">
              <button
                className="text-link"
                onClick={() => onExport("json", "preview")}
              >
                Скачать полный предпросмотр
              </button>
              <button className="text-link" onClick={() => inspect(csv)}>
                Заново сверить опрос
              </button>
            </div>
          )}
        </Notice>
      )}
      {preview ? (
        <>
          <div className="selection-bar">
            <span>Предпросмотр · ещё не сохранён</span>
            <Button kind="primary" disabled={busy} onClick={save}>
              Сохранить проверку
            </Button>
          </div>
          <ValidationMetrics result={preview.record.validation!.result} />
        </>
      ) : record.validation ? (
        <>
          <p className="help">
            Сохранено {date(record.validation.created_at)} · ответы
            предоставлены пользователем.
          </p>
          <ValidationMetrics result={record.validation.result} />
        </>
      ) : (
        <Notice>
          Живая проверка ещё не проведена. Добавьте ответы, чтобы измерить
          расхождение с симуляцией.
        </Notice>
      )}
      <p className="help">
        Ошибка взвешивается по числу ответов. Ранги сравниваются на составе
        загруженного опроса; для содержательных выводов оценивайте варианты на
        сопоставимых аудиториях.
      </p>
    </>
  );
}
