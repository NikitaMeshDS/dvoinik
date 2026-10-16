import { decimal, percent, Notice } from "../../components";
import type { Experiment } from "../../types";
import type { BaselineAgreement } from "./types";
const HOMOGENEOUS_SD = 0.05;
export default function BaselineCard({
  record,
  baseline,
}: {
  record: Experiment;
  baseline: BaselineAgreement | null | undefined;
}) {
  if (baseline === undefined) return null;
  const narrow = record.mock
    ? []
    : Object.entries(record.report).filter(
        ([, r]) => r.probability && r.probability.sd < HOMOGENEOUS_SD,
      );
  return (
    <section
      className="baseline-card"
      aria-label="Сравнение с простым подходом"
    >
      <div className="section-heading">
        <h2>Двойники и простой подход</h2>
        <span>
          {baseline?.method === "single_prompt"
            ? "Один запрос к модели без персонажей"
            : "Демо: правило без профилей"}
        </span>
      </div>
      {!baseline ? (
        <p className="help">
          Снимок создан до появления сравнения. Повторите запуск, чтобы получить
          оценку простым подходом.
        </p>
      ) : baseline.error ? (
        <Notice kind="error">
          Простой подход не дал оценку: {baseline.error} Результат двойников
          сохранён полностью.
        </Notice>
      ) : (
        <div className="baseline-grid">
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Предложение</th>
                  <th>Двойники</th>
                  <th>Простой подход</th>
                  <th>Разница</th>
                </tr>
              </thead>
              <tbody>
                {baseline.rows!.map((r) => (
                  <tr key={r.variant}>
                    <td>{r.variant}</td>
                    <td>{percent(r.twins)}</td>
                    <td>{percent(r.baseline)}</td>
                    <td>
                      {(r.twins >= r.baseline ? "+" : "") +
                        decimal((r.twins - r.baseline) * 100)}{" "}
                      п.п.
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="baseline-verdict">
            <span
              className={
                "chip " + (baseline.same_leader ? "chip-neutral" : "chip-warm")
              }
            >
              {baseline.same_leader ? "Лидер совпадает" : "Лидеры различаются"}
            </span>
            <p>
              Двойники: {baseline.twin_leaders!.join(", ")} · простой подход:{" "}
              {baseline.baseline_leaders!.join(", ")}
              {baseline.spearman !== null && baseline.spearman !== undefined
                ? " · корреляция рангов " + decimal(baseline.spearman, 2)
                : ""}
            </p>
            <p className="help">
              Если оба подхода дают одно и то же, персонажи не добавляют
              информации. Что ближе к людям, покажет живой опрос: после загрузки
              ответов ошибки обоих подходов сравниваются во вкладке «Проверка
              опросом».
            </p>
          </div>
        </div>
      )}
      {narrow.length > 0 && (
        <Notice kind="warning">
          Ответы персонажей однородны: разброс заявленной вероятности меньше{" "}
          {decimal(HOMOGENEOUS_SD * 100, 0)} п.п. в предложениях{" "}
          {narrow.map(([v]) => v).join(", ")}. Возможно, модель отвечает
          одинаково независимо от профиля.
        </Notice>
      )}
    </section>
  );
}
