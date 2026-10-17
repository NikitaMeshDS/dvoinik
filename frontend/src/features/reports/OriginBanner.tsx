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
}: {
  record: Experiment;
  stability?: Stability | null;
  plan?: LivePlan;
  onOpen?: (id: string) => void;
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
                ? "Гипотеза подтвердилась в симуляции"
                : verdict.kind === "same"
                  ? "Симуляция не различает варианты"
                  : "Гипотеза не подтвердилась в симуляции"}
            </h2>
            <p>
              B (новый текст) — {percent(verdict.b)}, A (текущий вариант{" "}
              {origin.variant}) — {percent(verdict.a)}:{" "}
              {verdict.gap > 0 ? "+" : "−"}
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
              {verdict.kind === "better"
                ? needed
                  ? "Дальше — живой тест: ≈ " +
                    needed.toLocaleString("ru-RU") +
                    " оценок на каждый вариант, план во вкладке «Проверка опросом»."
                  : "Дальше — живой тест, план во вкладке «Проверка опросом»."
                : verdict.kind === "same"
                  ? "Разница меньше 2 п.п.: изменение не стоит отдельного живого теста. Попробуйте другую гипотезу."
                  : "Оставьте текущий текст и попробуйте другую гипотезу из исходного исследования."}
            </p>
          </>
        ) : (
          <p>
            Основа — исследование «{origin.title}». Сравните запуски, чтобы
            увидеть, что изменилось в предложениях, аудитории и результатах.
          </p>
        )}
      </div>
      <div className="origin-actions">
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
