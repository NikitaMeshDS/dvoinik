import { decimal, percent } from "../../components";
import type { LivePlan as Plan } from "./types";
export default function LivePlan({
  plan,
  mock,
}: {
  plan: Plan | undefined;
  mock: boolean;
}) {
  return (
    <section className="live-plan" aria-label="План живой проверки">
      <div className="section-heading">
        <h2>
          <span className="validation-step" aria-hidden="true">
            1
          </span>{" "}
          Спланируйте проверку
        </h2>
        <span>Ориентир для исследователя</span>
      </div>
      {!plan ? (
        <p className="help">Готовим план…</p>
      ) : (
        <div className="live-plan-grid">
          <div>
            <h3>Сколько ответов нужно</h3>
            {plan.comparisons.length ? (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Сравнение</th>
                      <th>В симуляции</th>
                      <th>Оценок на предложение</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.comparisons.map((c) => (
                      <tr key={c.pair.join("-")}>
                        <td>
                          {c.pair[0]} против {c.pair[1]}
                        </td>
                        <td>
                          {percent(c.rates[0])} / {percent(c.rates[1])}
                          <small> · {decimal(c.gap_pp)} п.п.</small>
                        </td>
                        <td>
                          <strong>
                            {c.n_per_variant === null
                              ? "не различить"
                              : "≈ " + c.n_per_variant.toLocaleString("ru-RU")}
                          </strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="help">Для расчёта нужны два варианта с ответами.</p>
            )}
            <p className="plan-callout">
              Разведка на {plan.exploratory_n} оценках на предложение заметит
              только разницу от{" "}
              <strong>{decimal(plan.exploratory_detectable_pp)} п.п.</strong>{" "}
              Используйте её, чтобы проверить формулировки и причины, а не чтобы
              выбрать победителя.
            </p>
            {plan.focus_segments.length > 0 && (
              <>
                <h3>Проверить отдельно</h3>
                <ul className="plan-list">
                  {plan.focus_segments.map((s) => (
                    <li key={s.segment}>
                      <strong>{s.name}</strong>: в симуляции лидирует вариант{" "}
                      {s.leader} (+{decimal(s.gap_pp)} п.п. к общему лидеру)
                    </li>
                  ))}
                </ul>
              </>
            )}
            <p className="help">
              {plan.assumptions}
              {mock
                ? " Демо-доли получены по правилам: расчёт показывает механизм планирования."
                : ""}
            </p>
          </div>
          <div>
            <h3>Вопросы для интервью</h3>
            <ol className="plan-questions">
              {plan.questions.map((q) => (
                <li key={q.text}>
                  {q.text}
                  <small>{q.source}</small>
                </li>
              ))}
            </ol>
            <p className="help">
              Вопросы о прошлом опыте, а не о мнении. Причины взяты из
              синтетических ответов и требуют проверки на людях. План и вопросы
              входят в комплект опроса.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
