import { useState } from "react";
import { decimal } from "../../components";
import { plural } from "../../data";
import type { SurveyContrast, ValidationCell } from "../../types";

function points(delta: number) {
  const magnitude = decimal(Math.abs(delta));
  const sign = magnitude === decimal(0) ? "" : delta > 0 ? "+" : "−";
  return `${sign}${magnitude} п.п.`;
}

export default function SegmentSurveyComparison({
  cells,
  segment,
  contrasts = [],
}: {
  cells: ValidationCell[];
  segment: string;
  contrasts?: SurveyContrast[];
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
  const contrast = contrasts.find(
    ({ pair }) => pair[0] === first.variant && pair[1] === second.variant,
  );
  const model = contrast?.model_pair;
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
          <dd>{points((first.actual - second.actual) * 100)}</dd>
        </div>
        <div>
          <dt>
            {model ? "По общим профилям" : "По бинарным ответам симуляции"}
          </dt>
          <dd>
            {points(
              model?.gap_pp ?? (first.predicted - second.predicted) * 100,
            )}
          </dd>
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
      {model && (
        <p className="help">
          В парной оценке учтено профилей —{" "}
          {model.matched_n.toLocaleString("ru-RU")}. Расхождение с опросом —{" "}
          {decimal(model.absolute_error_pp)} п.п.
        </p>
      )}
      {contrast?.interval_95_pp ? (
        <p className="help" role="status">
          95% интервал по опросу —{" "}
          {contrast.interval_95_pp.map(points).join(" … ")}.{" "}
          {contrast.direction === "uncertain"
            ? "Направление различия пока неопределённо."
            : `Интервал указывает на более высокую долю ответов «да» у варианта ${contrast.direction}.`}
        </p>
      ) : (
        <p className="help">
          Описательное сравнение. Интервал доступен, если в протоколе указано
          случайное назначение одного варианта каждому участнику.
        </p>
      )}
    </section>
  );
}
