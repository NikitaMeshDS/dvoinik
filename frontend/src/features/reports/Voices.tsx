import { Notice } from "../../components";
import type { Experiment, Catalog } from "../../types";
export default function Voices({
  record,
  catalog,
  segment,
  setSegment,
  variant,
  setVariant,
  decision,
  setDecision,
}: {
  record: Experiment;
  catalog: Catalog;
  segment: string;
  setSegment: (s: string) => void;
  variant: string;
  setVariant: (s: string) => void;
  decision: string;
  setDecision: (s: string) => void;
}) {
  const variants = Object.keys(record.report),
    segments = Object.keys(record.scenario.population);
  const quotes = (record.report[variant]?.quotes ?? []).filter(
    (q) =>
      (segment === "all" || q.segment_id === segment) &&
      (decision === "all" || Boolean(q.decision) === (decision === "yes")),
  );
  return (
    <>
      <div className="section-heading">
        <h2>Голоса двойников</h2>
        <span>Сохранённая подборка объяснений</span>
      </div>
      <div className="filter-bar">
        <select
          aria-label="Предложение для голосов"
          value={variant}
          onChange={(e) => setVariant(e.target.value)}
        >
          {variants.map((v) => (
            <option key={v} value={v}>
              Предложение {v}
            </option>
          ))}
        </select>
        <select
          aria-label="Сегмент голосов"
          value={segment}
          onChange={(e) => setSegment(e.target.value)}
        >
          <option value="all">Все сегменты</option>
          {segments.map((s) => (
            <option key={s} value={s}>
              {catalog.segments[s]?.name ?? s}
            </option>
          ))}
        </select>
        <select
          aria-label="Решение двойников"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
        >
          <option value="all">Все решения</option>
          <option value="yes">Готовы подключить</option>
          <option value="no">Отказались</option>
        </select>
      </div>
      <div className="voice-grid">
        {quotes.length ? (
          quotes.map((q, i) => (
            <blockquote key={i} className="voice">
              <span className={q.decision ? "yes" : "no"}>
                {q.decision ? "Готовы подключить" : "Отказались"}
              </span>
              <p>«{q.quote}»</p>
              <cite>
                {q.who}
                <small>{q.segment}</small>
              </cite>
            </blockquote>
          ))
        ) : (
          <Notice>
            В сохранённой подборке нет таких ответов. Попробуйте другой фильтр.
          </Notice>
        )}
      </div>
      <p className="help">
        Это синтетические объяснения. Подборка не представляет все ответы
        аудитории.
      </p>
    </>
  );
}
