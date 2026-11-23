import { decimal, percent } from "../../components";
import type { PairedProbability } from "../../types";

function signed(value: number) {
  return (value > 0 ? "+" : "") + decimal(value);
}

export default function PairedComparison({
  pairs,
  total,
  mock,
}: {
  pairs: PairedProbability[];
  total: number;
  mock: boolean;
}) {
  return (
    <section className="live-plan" aria-label="Парное сравнение предложений">
      <div className="section-heading">
        <h2>Парное сравнение</h2>
        <span>Вся аудитория</span>
      </div>
      <p className="help">
        Средние оценки ответа «да» по профилям, для которых есть обе оценки.
        {mock && " В демо оценки рассчитываются по правилам."}
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Пара</th>
              <th scope="col">Средние оценки</th>
              <th scope="col">Разница, п. п.</th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((pair) => (
              <tr key={pair.variants.join("-")}>
                <th scope="row">
                  {pair.variants.join(" − ")}
                  <small className="paired-meta">
                    {pair.matched_n} из {total} профилей
                  </small>
                </th>
                <td>
                  {pair.means
                    ? pair.means.map((p) => percent(p)).join(" / ")
                    : "—"}
                </td>
                <td>
                  {pair.gap_pp == null ? (
                    "Нет полных пар"
                  ) : (
                    <strong>{signed(pair.gap_pp)}</strong>
                  )}
                  {pair.interval_95_pp && (
                    <small className="paired-meta">
                      95% интервал {pair.interval_95_pp.map(signed).join(" … ")}
                    </small>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="help">
        Интервал отражает разброс при повторной выборке этих профилей. Точность
        прогноза по ответам людей проверяется опросом.
      </p>
    </section>
  );
}
