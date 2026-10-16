import type { Experiment, Catalog, Profile } from "../../types";
export default function Audience({
  record,
  catalog,
}: {
  record: Experiment;
  catalog: Catalog;
}) {
  const groups = Object.keys(record.population_counts).map((sid) => ({
    sid,
    profiles: record.population_sample.filter(
      (p: Profile) => p.segment === sid,
    ),
  }));
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
      {groups.map(({ sid, profiles }) => (
        <section className="profile-group" key={sid}>
          <div className="profile-group-heading">
            <h3>{catalog.segments[sid]?.name ?? sid}</h3>
            <span>
              <strong>
                {record.population_counts[sid].toLocaleString("ru-RU")}
              </strong>{" "}
              профилей в запуске
            </span>
          </div>
          {profiles.length ? (
            <div className="profile-grid">
              {profiles.map((p) => (
                <article className="profile" key={p.id}>
                  <div>
                    <span className="profile-avatar">{p.name[0]}</span>
                    <div>
                      <h4>
                        {p.name}, {p.age}
                      </h4>
                      <small>{p.region}</small>
                    </div>
                  </div>
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
          ) : (
            <p className="help">
              В снимке нет примеров профилей этого сегмента.
            </p>
          )}
        </section>
      ))}
    </>
  );
}
