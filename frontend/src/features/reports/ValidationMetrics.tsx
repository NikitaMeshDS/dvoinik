import { percent } from "../../components";
import type { ValidationResult } from "../../types";
export default function ValidationMetrics({
  result,
}: {
  result: ValidationResult;
}) {
  return (
    <>
      <div className="validation-metrics">
        <div>
          <span>Ошибка долей</span>
          <strong>
            {(result.mae_conversion * 100).toFixed(1)} <small>п.п.</small>
          </strong>
        </div>
        <div>
          <span>Корреляция рангов</span>
          <strong>
            {result.spearman_variants === null
              ? "—"
              : result.spearman_variants.toFixed(2)}
          </strong>
        </div>
        <div>
          <span>Совпадение лидера</span>
          <strong>
            {result.winner_match === null
              ? "Не определено"
              : result.winner_match
                ? "Да"
                : "Нет"}
          </strong>
        </div>
      </div>
      <p className="help">
        {result.survey_n} ответов опроса · {result.matched_cells} пар «вариант —
        сегмент». Это оценки предложений, а не число уникальных людей.
        Подлинность опроса приложение не проверяет.
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Вариант</th>
              <th>Сегмент</th>
              <th>Ответов</th>
              <th>Опрос</th>
              <th>Симуляция</th>
              <th>Ошибка</th>
            </tr>
          </thead>
          <tbody>
            {result.cells.map((c) => (
              <tr key={c.variant + c.segment}>
                <td>{c.variant}</td>
                <td>{c.segment}</td>
                <td>{c.survey_n}</td>
                <td>{percent(c.actual)}</td>
                <td>{percent(c.predicted)}</td>
                <td>{percent(c.error)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
