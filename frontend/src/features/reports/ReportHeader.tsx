import {
  ArrowRight,
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
import type { Experiment } from "../../types";
import type { Insights, ExportAction } from "./types";
export default function ReportHeader({
  record,
  base,
  onBack,
  onReuse,
  onCompare,
  pending,
  onRetry,
  onExport: exportFile,
}: {
  record: Experiment;
  base: Insights | null;
  onBack: () => void;
  onReuse: () => void;
  onCompare: () => void;
  pending?: string;
  onRetry?: () => void;
  onExport: ExportAction;
}) {
  const variants = Object.keys(record.report),
    segments = Object.keys(record.scenario.population),
    summary = base?.summary;
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
          <ul className="quality-checks" aria-label="Проверки качества">
            <li className={base.stability?.level ?? "muted"}>
              Устойчивость лидера:{" "}
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
