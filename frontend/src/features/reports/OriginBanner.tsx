import { ArrowUpRight, GitCompare } from "lucide-react";
import { decimal, percent } from "../../components";
import type { Experiment } from "../../types";
import type { LivePlan, Stability } from "./types";

const SAME_PP = 2;

/** Итог A/B-проверки гипотезы: B (новый текст) против A (текущий вариант). */
export function hypothesisVerdict(record: Experiment) {
  const a = record.report.A,
    b = record.report.B;
  if (!a?.n || !b?.n || a.conversion === null || b.conversion === null)
    return null;
  const gap = (b.conversion - a.conversion) * 100;
  const kind: "better" | "same" | "worse" =
    Math.abs(gap) < SAME_PP ? "same" : gap > 0 ? "better" : "worse";
  return { kind, gap, a: a.conversion, b: b.conversion };
}

export default function OriginBanner({
  record,
  stability,
  plan,
  onOpen,
  onCompare,
  onValidation,
}: {
  record: Experiment;
  stability?: Stability | null;
  plan?: LivePlan;
  onOpen?: (id: string) => void;
  onValidation?: () => void;
  onCompare?: (id: string) => void;
}) {
  const origin = record.scenario.origin;
  if (!origin) return null;
  const verdict =
    origin.kind === "hypothesis" ? hypothesisVerdict(record) : null;
  const needed = plan?.comparisons[0]?.n_per_variant;
  return (
    <section
      className={"origin-banner " + (verdict?.kind ?? "iteration")}
      aria-label="Связь с исходным исследованием"
    >
      <div className="origin-body">
        <span className="mini-label">
          {origin.kind === "hypothesis"
            ? "Проверка гипотезы «" + origin.lever + "»"
            : "Следующая итерация"}
        </span>
        {verdict ? (
          <>
            <h2>
              {verdict.kind === "better"
                ? "В симуляции чаще выбирали B"
                : verdict.kind === "same"
                  ? "В симуляции оценки A и B близки"
                  : "В симуляции чаще выбирали A"}
            </h2>
            <p>
              B (новый текст) — {percent(verdict.b)}, A (текущий вариант{" "}
              {origin.variant}) — {percent(verdict.a)}:{" "}
              {verdict.gap > 0 ? "+" : verdict.gap < 0 ? "−" : ""}
              {decimal(Math.abs(verdict.gap))} п.п.
              {verdict.kind === "better" &&
              stability &&
              stability.leader === "B"
                ? " B впереди в " +
                  decimal(stability.share * 100, 0) +
                  "% повторных выборок."
                : ""}
            </p>
            <p className="origin-next">
              {record.validation ? (
                <>
                  В загруженном опросе оценок:{" "}
                  {record.validation.result.survey_n}. Разницу по группам и
                  размеры выборок смотрите в проверке опросом.
                </>
              ) : (
                <>
                  Ответы людей пока не загружены. Какой текст получит больше
                  согласий в опросе?
                  {needed
                    ? " Для проверки разницы из симуляции ориентир — ≈ " +
                      needed.toLocaleString("ru-RU") +
                      " оценок на каждый вариант."
                    : ""}
                </>
              )}
            </p>
            {plan?.focus_segments.map((s) => (
              <p key={s.segment}>
                В сегменте «{s.name}» симуляция отдаёт преимущество варианту{" "}
                {s.leader} ({decimal(s.gap_pp)} п.п.).
              </p>
            ))}
          </>
        ) : (
          <p>
            Основа — исследование «{origin.title}». Сравните запуски, чтобы
            увидеть, что изменилось в предложениях, аудитории и результатах.
          </p>
        )}
      </div>
      <div className="origin-actions">
        {verdict && onValidation && (
          <button className="text-link with-icon" onClick={onValidation}>
            {record.validation
              ? "Посмотреть ответы опроса"
              : "Подготовить проверку"}
          </button>
        )}
        {onCompare && origin.kind === "iteration" && (
          <button
            className="text-link with-icon"
            onClick={() => onCompare(origin.record_id)}
          >
            <GitCompare size={15} aria-hidden="true" />
            Сравнить с исходным
          </button>
        )}
        {onOpen && (
          <button
            className="text-link with-icon"
            onClick={() => onOpen(origin.record_id)}
          >
            <ArrowUpRight size={15} aria-hidden="true" />
            Открыть исходное исследование
          </button>
        )}
      </div>
    </section>
  );
}
