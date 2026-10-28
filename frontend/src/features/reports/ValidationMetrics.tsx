import { decimal, percent } from "../../components";
import type { Catalog, ValidationResult } from "../../types";
export default function ValidationMetrics({
  result,
  segments,
}: {
  result: ValidationResult;
  segments: Catalog["segments"];
}) {
  return (
    <>
      <div className="validation-metrics">
        <div>
          <span>Ошибка долей</span>
          <strong>
            {decimal(result.mae_conversion * 100)} <small>п.п.</small>
          </strong>
        </div>
        <div>
          <span>Корреляция рангов</span>
          <strong>
            {result.spearman_variants === null
              ? "—"
              : decimal(result.spearman_variants, 2)}
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
        Оценок: {result.survey_n} · Пар «вариант — сегмент»:{" "}
        {result.matched_cells}. Это оценки предложений, а не число уникальных
        людей. Подлинность опроса приложение не проверяет.
      </p>
      {result.baseline && (
        <div className="baseline-validation">
          <h3>Двойники против простого подхода</h3>
          <div className="validation-metrics compact">
            <div>
              <span>Ошибка двойников</span>
              <strong>
                {decimal(result.baseline.twins_mae_variants * 100)}{" "}
                <small>п.п.</small>
              </strong>
            </div>
            <div>
              <span>Ошибка простого подхода</span>
              <strong>
                {decimal(result.baseline.baseline_mae_variants * 100)}{" "}
                <small>п.п.</small>
              </strong>
            </div>
            <div>
              <span>Кто ближе к опросу</span>
              <strong>
                {Math.abs(
                  result.baseline.twins_mae_variants -
                    result.baseline.baseline_mae_variants,
                ) < 0.005
                  ? "Одинаково"
                  : result.baseline.twins_mae_variants <
                      result.baseline.baseline_mae_variants
                    ? "Двойники"
                    : "Простой подход"}
              </strong>
            </div>
          </div>
          <p className="help">
            Сравнение по предложениям с весами опроса. Простой подход оценивает
            всю аудиторию сразу: если опрос покрывает не все сегменты,
            сопоставление приблизительное. Один опрос — разведка, а не
            доказательство преимущества.
          </p>
        </div>
      )}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Вариант</th>
              <th>Сегмент</th>
              <th>Оценок</th>
              <th>Опрос</th>
              <th>Симуляция</th>
              <th>Ошибка</th>
            </tr>
          </thead>
          <tbody>
            {result.cells.map((c) => (
              <tr key={c.variant + c.segment}>
                <td>{c.variant}</td>
                <td className="validation-segment">
                  {segments[c.segment]?.name ?? c.segment}
                  {segments[c.segment] && <small>{c.segment}</small>}
                </td>
                <td>{c.survey_n}</td>
                <td>{percent(c.actual)}</td>
                <td>{percent(c.predicted)}</td>
                <td>{decimal(c.error * 100)} п.п.</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
