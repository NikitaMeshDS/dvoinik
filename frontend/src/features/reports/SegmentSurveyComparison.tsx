import { useState } from "react";
import { decimal } from "../../components";
import { plural } from "../../data";
import type { ValidationCell } from "../../types";

function difference(first: number, second: number) {
  const delta = (first - second) * 100;
  const magnitude = decimal(Math.abs(delta));
  const sign = magnitude === decimal(0) ? "" : delta > 0 ? "+" : "−";
  return `${sign}${magnitude} п.п.`;
}

export default function SegmentSurveyComparison({
  cells,
  segment,
}: {
  cells: ValidationCell[];
  segment: string;
}) {
  const [selected, setSelected] = useState("");
  const variants = [...cells].sort((a, b) =>
    a.variant.localeCompare(b.variant),
  );
  const pairs = variants.flatMap((first, index) =>
    variants.slice(index + 1).map((second) => ({
      id: first.variant + "-" + second.variant,
      first,
      second,
    })),
  );
  const pair = pairs.find(({ id }) => id === selected) ?? pairs[0];
  if (!pair) return null;
  const { first, second } = pair;
  return (
    <section
      className="segment-survey-comparison"
      aria-label="Сравнение предложений в сегменте"
    >
      <div className="segment-survey-comparison-heading">
        <div>
          <h4>
            Разница {first.variant} − {second.variant}
          </h4>
          <p className="help">{segment}</p>
        </div>
        {pairs.length > 1 && (
          <label className="field">
            <span>Пара для сравнения</span>
            <select
              value={pair.id}
              onChange={(event) => setSelected(event.target.value)}
            >
              {pairs.map(({ id, first, second }) => (
                <option key={id} value={id}>
                  {first.variant} и {second.variant}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <dl className="segment-survey-differences">
        <div>
          <dt>По ответам опроса</dt>
          <dd>{difference(first.actual, second.actual)}</dd>
        </div>
        <div>
          <dt>По симуляции</dt>
          <dd>{difference(first.predicted, second.predicted)}</dd>
        </div>
      </dl>
      <ul className="segment-survey-counts" aria-label="Число оценок в опросе">
        {[first, second].map(({ variant, survey_n }) => (
          <li key={variant}>
            {variant} — {survey_n.toLocaleString("ru-RU")}{" "}
            {plural(survey_n, "оценка", "оценки", "оценок")}
          </li>
        ))}
      </ul>
      <p className="help">
        Сравнение описательное. Учитывайте число оценок и способ распределения
        участников.
      </p>
    </section>
  );
}
