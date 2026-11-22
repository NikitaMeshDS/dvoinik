import { ScanText, ChartNoAxesCombined } from "lucide-react";
import { decimal, percent } from "../../components";
import { plural } from "../../data";
import type { Experiment } from "../../types";
import type { Insights } from "./types";
import type { nextStep } from "./nextStep";
export default function ResearchBrief({
  record,
  base,
  analyticsError,
  hasQualityIssue,
  next,
}: {
  record: Experiment;
  base: Insights | null;
  analyticsError: string;
  hasQualityIssue: boolean;
  next: ReturnType<typeof nextStep>;
}) {
  const summary = base?.summary;
  const variants = Object.keys(record.scenario.variants);
  const survey = record.validation?.result;
  const expectedPairs =
    variants.length *
    Object.values(record.scenario.population).filter((weight) => weight > 0)
      .length;
  const surveyTitle = !survey
    ? "Опрос ещё не загружен"
    : survey.matched_cells < expectedPairs
      ? "Неполное покрытие опроса"
      : "Опрос загружен";
  const observation = hasQualityIssue
    ? "Есть пропуски, ошибки или корректировки ответов. Проверьте качество перед сравнением вариантов."
    : !summary
      ? analyticsError
        ? "Аналитика недоступна. Сохранённые ответы остаются в отчёте."
        : "Загружаем разбор сохранённых ответов…"
      : !summary.leaders.length
        ? "Нет валидных ответов для сравнения. Проверьте подключение и настройки модели."
        : summary.leaders.length > 1
          ? `У вариантов ${summary.leaders.join(" / ")} одинаковая доля ответов «да» — ${percent(summary.best)}.`
          : `Вариант ${summary.leaders[0]} получил ${percent(summary.best)} ответов «да»${summary.gap_pp > 0 ? ` — выше следующего на ${decimal(summary.gap_pp)} п. п.` : "."}`;
  return (
    <section className="research-brief" aria-label="Краткий итог исследования">
      <div className="brief-sources" role="group" aria-label="Источники данных">
        <div>
          <strong>
            {record.mock ? "Эвристическое демо" : "Симуляция модели"}
          </strong>
          <span>{record.mock ? "По заданным правилам" : record.model}</span>
        </div>
        <div>
          <strong>{surveyTitle}</strong>
          {survey && (
            <span>
              {survey.survey_n.toLocaleString("ru-RU")}{" "}
              {plural(survey.survey_n, "оценка", "оценки", "оценок")} ·{" "}
              {survey.matched_cells} из {expectedPairs} пар «предложение —
              сегмент»
            </span>
          )}
        </div>
      </div>
      <div className="brief-question">
        <h2>
          <ScanText size={18} aria-hidden="true" />
          Что сравнивали
        </h2>
        <p>{record.scenario.question}</p>
        <span className="brief-caption">
          {variants.length}{" "}
          {plural(variants.length, "предложение", "предложения", "предложений")}{" "}
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
          <h2>{next.title}</h2>
          <p>{next.detail}</p>
        </div>
      </section>
    </section>
  );
}
