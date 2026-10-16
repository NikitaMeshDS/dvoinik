import type { Experiment, Catalog } from "../../types";
export default function Audience({
  record,
  catalog,
}: {
  record: Experiment;
  catalog: Catalog;
}) {
  return (
    <>
      <div className="section-heading">
        <h2>Профили аудитории</h2>
        <span>До трёх примеров на сегмент</span>
      </div>
      <p className="help">
        Синтетические характеристики основаны на экспертных предположениях.
        Калибровка ещё не подтверждена.
      </p>
      <div className="profile-grid">
        {record.population_sample.map((p) => (
          <article className="profile" key={p.segment + "-" + p.id}>
            <div>
              <span className="profile-avatar">{p.name[0]}</span>
              <div>
                <h3>
                  {p.name}, {p.age}
                </h3>
                <small>{p.region}</small>
              </div>
              <span className="profile-count">
                {record.population_counts[p.segment]}
                <small>профилей</small>
              </span>
            </div>
            <h4>{catalog.segments[p.segment]?.name ?? p.segment}</h4>
            <p>{p.income}</p>
            <div className="habit-tags">
              {p.habits.map((h) => (
                <span key={h}>{h}</span>
              ))}
            </div>
            <p className="help">{p.attitude}</p>
          </article>
        ))}
      </div>
    </>
  );
}
