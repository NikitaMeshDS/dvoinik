import type { Experiment } from "../../types";
export default function SnapshotDetails({ record }: { record: Experiment }) {
  const results = Object.values(record.report);
  const valid = results.reduce((sum, result) => sum + result.n, 0);
  const errors = results.reduce((sum, result) => sum + result.failed_n, 0);
  return (
    <details className="disclosure">
      <summary>Предложения и настройки сохранённого снимка</summary>
      <div className="disclosure-content">
        <p>
          <strong>Вопрос:</strong> {record.scenario.question}
        </p>
        <p>{record.scenario.description}</p>
        {record.scenario.deposit_minimum_rub !== undefined && (
          <p>
            Минимальный взнос —{" "}
            {record.scenario.deposit_minimum_rub.toLocaleString("ru-RU")} ₽.
          </p>
        )}
        <div className="saved-offers">
          {Object.entries(record.scenario.variants).map(([v, text]) => (
            <div key={v} className={"variant-" + v}>
              <b>Предложение {v}</b>
              <p>{text}</p>
            </div>
          ))}
        </div>
        <h3>Фактическая нагрузка</h3>
        <p>
          {record.elapsed_seconds > 0 &&
            `Время ${record.elapsed_seconds.toLocaleString("ru-RU")} с · `}
          Валидных ответов {valid} · Ошибок ответов {errors}
        </p>
        <ModelUsage record={record} />
        <p className="help">
          Seed {record.seed} · {record.model} · ID {record.id}
        </p>
      </div>
    </details>
  );
}

function ModelUsage({ record }: { record: Experiment }) {
  const usage = record.run_usage;
  if (!usage) return <p>Учёт обращений к модели в этом снимке отсутствует.</p>;
  if (record.mock) return <p>Демо прошло без обращений к модели.</p>;
  if (usage.sdk_calls === 0)
    return <p>Вызовов модели не было. Ответов из кэша {usage.cache_hits}.</p>;
  return (
    <>
      <p>
        Параллельность {usage.concurrency} · Вызовов SDK {usage.sdk_calls} ·
        Ответов из кэша {usage.cache_hits}
      </p>
      <p>
        {usage.reported_tokens === null
          ? "Данные о расходе токенов отсутствуют."
          : `Провайдер учёл ${usage.reported_tokens.toLocaleString("ru-RU")} токенов по ${usage.calls_with_usage} из ${usage.sdk_calls} вызовов.`}
      </p>
    </>
  );
}
