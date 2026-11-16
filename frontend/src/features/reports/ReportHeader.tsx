import {
  ArrowRight,
  FileText,
  FileJson,
  FileSpreadsheet,
  GitCompare,
  RefreshCw,
} from "lucide-react";
import {
  Back,
  Heading,
  Button,
  Menu,
  Notice,
  date,
  decimal,
  percent,
} from "../../components";
import { nextStep } from "./nextStep";
import type { Experiment } from "../../types";
import type { Insights, ExportAction } from "./types";
export default function ReportHeader({
  record,
  base,
  onBack,
  onReuse,
  onCompare,
  onValidation,
  pending,
  onRetry,
  onExport: exportFile,
}: {
  record: Experiment;
  base: Insights | null;
  onBack: () => void;
  onReuse: () => void;
  onCompare: () => void;
  onValidation?: () => void;
  pending?: string;
  onRetry?: () => void;
  onExport: ExportAction;
}) {
  const variants = Object.keys(record.report),
    segments = Object.keys(record.scenario.population),
    summary = base?.summary;
  const corrected = Object.entries(record.report).filter(
    ([, result]) => (result.inconsistent_n ?? 0) > 0,
  );
  const next = nextStep(record, pending);
  const nextAction =
    next.action === "save"
      ? (onRetry ?? (() => exportFile("json")))
      : next.action === "reuse"
        ? onReuse
        : (onValidation ?? onReuse);
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
            <Button onClick={onReuse}>
              Следующая итерация
              <ArrowRight size={18} />
            </Button>
            <Menu label="Действия с отчётом">
              <button onClick={() => exportFile("html", "summary")}>
                <FileText size={17} />
                Резюме для команды
              </button>
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
      <section
        className="report-next-step"
        aria-label="Следующий шаг исследования"
      >
        <div>
          <h2>{next.title}</h2>
          <p>{next.detail}</p>
        </div>
        <Button kind="primary" onClick={nextAction}>
          {next.action === "save" && !onRetry
            ? "Скачать полный JSON"
            : next.label}
          <ArrowRight size={18} />
        </Button>
      </section>
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
      {corrected.length > 0 && (
        <Notice kind="warning">
          <strong>Модель неоднозначно указала вероятность согласия.</strong>
          <p>
            Ответ «да/нет» расходился с вероятностью. При обработке таких
            ответов приложение заменило вероятность p на 1 − p. Итоговые
            показатели включают эту корректировку.
          </p>
          <ul aria-label="Корректировки вероятностей по вариантам">
            {corrected.map(([variant, result]) => (
              <li key={variant}>
                Вариант {variant}: {result.inconsistent_n} из {result.n} ответов
                {result.n > 0
                  ? " (" + percent(result.inconsistent_n! / result.n) + ")"
                  : ""}
                {result.raw_probability && result.probability
                  ? ` — Средняя вероятность по всем ${result.n} валидным ответам до корректировки: ${percent(result.raw_probability.mean)}; после: ${percent(result.probability.mean)}.`
                  : " — Исходные значения не сохранены; среднее до корректировки неизвестно."}
              </li>
            ))}
          </ul>
          <p>
            Проверьте формулировку запроса и повторите запуск с однозначным
            форматом ответа перед интерпретацией различий.
          </p>
        </Notice>
      )}
      {base && (
        <div className={"quality-note " + base.quality.kind}>
          <span />
          <div>
            <strong>{base.quality.title}</strong>
            <p>{base.quality.detail}</p>
          </div>
          <ul className="quality-checks" aria-label="Проверки качества">
            <li className={base.stability?.level ?? "muted"}>
              Лидер в повторных выборках:{" "}
              {base.stability
                ? decimal(base.stability.share * 100, 0) + "%"
                : "нужны два варианта"}
            </li>
            <li
              className={
                !base.baseline || base.baseline.error
                  ? "muted"
                  : base.baseline.same_leader
                    ? "stable"
                    : "moderate"
              }
            >
              Простой подход:{" "}
              {!base.baseline
                ? "нет в снимке"
                : base.baseline.error
                  ? "ошибка запроса"
                  : base.baseline.same_leader
                    ? "лидер совпадает"
                    : "лидеры различаются"}
            </li>
            <li className={record.validation ? "stable" : "muted"}>
              Живой опрос:{" "}
              {record.validation
                ? "ошибка " +
                  decimal(record.validation.result.mae_conversion * 100) +
                  " п.п."
                : "ещё не загружен"}
            </li>
          </ul>
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
            {summary?.leaders.length ? percent(summary.best) : "—"}
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
            {summary ? decimal(summary.gap_pp) : "—"} <small>п.п.</small>
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
    </>
  );
}
