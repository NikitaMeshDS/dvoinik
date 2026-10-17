import { percent } from "../../components";
import { COLORS, type ReportItem } from "../../types";

const LABELS = ["Точно нет", "Скорее нет", "Не знаю", "Скорее да", "Точно да"];

/** Распределение ответов по шкале 1–5 в режиме SSR. */
export default function LikertBars({
  report,
}: {
  report: Record<string, ReportItem>;
}) {
  const rows = Object.entries(report).filter(
    ([, r]) => r.likert && r.likert.length === 5,
  );
  if (!rows.length) return null;
  return (
    <section className="likert" aria-label="Распределение ответов по шкале">
      <div className="likert-head">
        <h3>Ответы по шкале 1–5</h3>
        <span>SSR: оценка по смыслу ответа, а не по названному числу</span>
      </div>
      {rows.map(([vid, r], i) => (
        <div className="likert-row" key={vid}>
          <span className="likert-variant" style={{ color: COLORS[i] }}>
            {vid}
          </span>
          <div
            className="likert-bar"
            role="img"
            aria-label={
              "Вариант " +
              vid +
              ": " +
              LABELS.map((l, k) => l + " " + percent(r.likert![k])).join(", ")
            }
          >
            {r.likert!.map((share, k) => (
              <i
                key={k}
                className={"likert-" + k}
                style={{ width: share * 100 + "%" }}
                title={LABELS[k] + ": " + percent(share)}
              />
            ))}
          </div>
        </div>
      ))}
      <div className="likert-legend" aria-hidden="true">
        {LABELS.map((label, k) => (
          <span key={label}>
            <i className={"likert-" + k} />
            {label}
          </span>
        ))}
      </div>
    </section>
  );
}
