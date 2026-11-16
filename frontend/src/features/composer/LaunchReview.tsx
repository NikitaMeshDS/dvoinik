import { percent } from "../../components";
import { VARIANTS, type Catalog, type Draft } from "../../types";
export default function LaunchReview({
  draft,
  catalog,
  counts,
  onEdit,
}: {
  draft: Draft;
  catalog: Catalog;
  counts?: Record<string, number>;
  onEdit: () => void;
}) {
  const offers = VARIANTS.slice(0, draft.variantCount);
  const groups = new Map<string, string[]>();
  for (const v of offers) {
    const text = (draft.variants[v] ?? "")
      .trim()
      .replace(/\s+/gu, " ")
      .toLocaleLowerCase("ru-RU");
    if (text) groups.set(text, [...(groups.get(text) ?? []), v]);
  }
  const duplicates = [...groups.values()].filter((g) => g.length > 1);
  const audience = Object.entries(draft.weights).filter(([, w]) => w > 0),
    sum = audience.reduce((n, [, w]) => n + w, 0);
  return (
    <section className="launch-review" aria-label="Проверьте перед запуском">
      <div className="section-heading">
        <h2>Проверьте перед запуском</h2>
        <button className="text-link" onClick={onEdit}>
          Изменить вопрос и предложения
        </button>
      </div>
      <h3>{draft.title}</h3>
      <p>{draft.question}</p>
      <dl className="launch-review-facts">
        <div>
          <dt>Режим</dt>
          <dd>
            {draft.mock ? "Демо без внешних запросов" : "Подключённая LLM"}
          </dd>
        </div>
        <div>
          <dt>Объём</dt>
          <dd>
            {draft.n.toLocaleString("ru-RU")} профилей × {offers.length}{" "}
            предложения = {(draft.n * offers.length).toLocaleString("ru-RU")}{" "}
            оценок
          </dd>
        </div>
        <div>
          <dt>Параметры</dt>
          <dd>
            Seed {draft.seed} · параллельность {draft.concurrency}
          </dd>
        </div>
      </dl>
      <ul className="launch-review-audience">
        {audience.map(([sid, w]) => (
          <li key={sid}>
            {catalog.segments[sid]?.name ?? sid}: {percent(w / sum)}
            {counts?.[sid] !== undefined
              ? ` · ${counts[sid]} профилей`
              : " · точное число профилей уточняется"}
          </li>
        ))}
      </ul>
      {duplicates.map((group) => (
        <p className="launch-review-warning" key={group.join(",")}>
          Совпадают тексты предложений: {group.join(", ")} (без учёта регистра и
          пробелов). Такой запуск проверит повторяемость ответов, но не различие
          текстов.
        </p>
      ))}
      <details className="disclosure">
        <summary>Сверить тексты предложений ({offers.length})</summary>
        <div className="disclosure-content">
          {offers.map((v) => (
            <div key={v}>
              <h4>Предложение {v}</h4>
              <p className="launch-review-offer">{draft.variants[v]}</p>
            </div>
          ))}
        </div>
      </details>
      <p className="help">
        {draft.mock
          ? "Результаты демо показывают процесс; прогноз спроса ими не проверяется."
          : "Тексты и синтетические профили будут переданы модели, настроенной администратором. Новое исследование начнётся после нажатия кнопки запуска."}
      </p>
    </section>
  );
}
