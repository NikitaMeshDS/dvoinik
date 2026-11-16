import type { Catalog, Experiment, ValidationResult } from "../../types";
import { percent } from "../../components";

/** Describes observed sample coverage; does not infer representativeness or unique people. */
export default function SurveyCoverage({
  record,
  result,
  segments,
}: {
  record: Experiment;
  result: ValidationResult;
  segments: Catalog["segments"];
}) {
  const variants = Object.keys(record.scenario.variants);
  const selected = Object.entries(record.scenario.population)
    .filter(([, w]) => w > 0)
    .map(([sid]) => sid);
  const counts = new Map<string, number>();
  for (const cell of result.cells)
    counts.set(JSON.stringify([cell.variant, cell.segment]), cell.survey_n);
  const count = (variant: string, sid: string) =>
    counts.get(JSON.stringify([variant, sid])) ?? 0;
  const total = (variant: string) =>
    selected.reduce((n, sid) => n + count(variant, sid), 0);
  const covered = variants.reduce(
    (n, v) => n + selected.filter((sid) => count(v, sid) > 0).length,
    0,
  );
  const expected = variants.length * selected.length;
  const missing = variants.filter((v) => total(v) === 0);
  const complete = expected > 0 && covered === expected;
  const comparable =
    complete &&
    variants.length > 1 &&
    variants.every((v) =>
      selected.every(
        (sid) =>
          Math.abs(
            count(v, sid) / total(v) -
              count(variants[0], sid) / total(variants[0]),
          ) < 1e-9,
      ),
    );
  return (
    <section
      className="survey-coverage"
      aria-label="Покрытие загруженного опроса"
    >
      <h3>Кого охватывает опрос</h3>
      <p>
        <strong>
          {covered} из {expected} пар «предложение — сегмент»
        </strong>
      </p>
      {missing.length > 0 && (
        <p className="coverage-warning">
          Нет оценок предложений: {missing.join(", ")}. Сравнение всех
          предложений невозможно.
        </p>
      )}
      {!complete && (
        <p className="coverage-warning">
          Часть выбранной аудитории не покрыта. Метрики ниже относятся только к
          загруженным парам; отсутствие ответов не означает отказ.
        </p>
      )}
      {complete && variants.length > 1 && (
        <p>
          {comparable
            ? "Доли сегментов одинаковы у всех предложений, число оценок может различаться."
            : "Состав аудитории различается между предложениями. Разница долей согласий может быть связана с составом групп; проверьте схему набора и распределения участников."}
        </p>
      )}
      <div
        className="table-scroll"
        role="region"
        aria-label="Число оценок и доля сегментов по предложениям"
        tabIndex={0}
      >
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Предложение</th>
              <th scope="col">Оценок</th>
              {selected.map((sid) => (
                <th key={sid} scope="col">
                  {segments[sid]?.name ?? sid}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {variants.map((v) => (
              <tr key={v}>
                <th scope="row">{v}</th>
                <td>{total(v) || "Нет ответов"}</td>
                {selected.map((sid) => (
                  <td key={sid}>
                    {count(v, sid) > 0 ? (
                      <>
                        {count(v, sid)}{" "}
                        <small>({percent(count(v, sid) / total(v))})</small>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="help">
        Проценты — доля сегмента среди оценок каждого предложения. Полное
        покрытие не подтверждает репрезентативность, независимость ответов или
        достаточный размер выборки. Это оценки предложений; число уникальных
        людей и способ распределения нужно сверить с протоколом исследования.
      </p>
    </section>
  );
}
