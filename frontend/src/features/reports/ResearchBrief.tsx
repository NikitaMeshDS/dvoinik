import { ArrowRight, ScanText, ChartNoAxesCombined } from "lucide-react";
import { Button, percent } from "../../components";
import { plural } from "../../data";
import type { Experiment } from "../../types";
import type { Insights } from "./types";
import { nextStep } from "./nextStep";
export default function ResearchBrief({
  record,
  base,
  analyticsError,
  next,
  actionLabel,
  onAction,
}: {
  record: Experiment;
  base: Insights | null;
  analyticsError: string;
  next: ReturnType<typeof nextStep>;
  actionLabel: string;
  onAction: () => void;
}) {
  const summary = base?.summary;
  const observation =
    nextStep(record).action === "reuse"
      ? "Есть пропуски, ошибки или корректировки ответов. Проверьте качество перед сравнением вариантов."
      : !summary
        ? analyticsError
          ? "Аналитика недоступна. Сохранённые ответы остаются в отчёте."
          : "Загружаем разбор сохранённых ответов…"
        : !summary.leaders.length
          ? "Нет валидных ответов для сравнения. Проверьте подключение и настройки модели."
          : summary.leaders.length > 1
            ? `Варианты ${summary.leaders.join(" / ")} получили равную долю согласий: ${percent(summary.best)}.`
            : `В симуляции наибольшая доля согласий у ${summary.leaders[0]}: ${percent(summary.best)}.`;
  return (
    <section className="research-brief" aria-label="Краткий итог исследования">
      <div className="brief-question">
        <h2>
          <ScanText size={18} aria-hidden="true" />
          Что сравнивали
        </h2>
        <p>{record.scenario.question}</p>
        <span className="brief-caption">
          {Object.keys(record.scenario.variants).length}{" "}
          {plural(
            Object.keys(record.scenario.variants).length,
            "предложение",
            "предложения",
            "предложений",
          )}{" "}
          · {record.n.toLocaleString("ru-RU")} синтетических профилей
        </span>
        <details className="brief-offers">
          <summary>Тексты предложений</summary>
          <dl>
            {Object.entries(record.scenario.variants).map(([letter, text]) => (
              <div key={letter}>
                <dt>{letter}</dt>
                <dd>{text}</dd>
              </div>
            ))}
          </dl>
        </details>
      </div>
      <div className="brief-observation">
        <h2>
          <ChartNoAxesCombined size={18} aria-hidden="true" />
          Что увидели
        </h2>
        <p>{observation}</p>
        <span className="brief-caption">
          {record.mock
            ? "Демонстрация по правилам, не прогноз спроса."
            : "Синтетические ответы, не прогноз спроса. Разницу нужно проверить на людях."}
        </span>
      </div>
      <section
        className="report-next-step"
        aria-label="Следующий шаг исследования"
      >
        <div>
          <span className="brief-next-label">Что дальше</span>
          <h2>{next.title}</h2>
          <p>{next.detail}</p>
        </div>
        <Button kind="primary" onClick={onAction}>
          {actionLabel}
          <ArrowRight size={17} aria-hidden="true" />
        </Button>
      </section>
    </section>
  );
}
