import type { Experiment } from "../../types";
export default function SnapshotDetails({ record }: { record: Experiment }) {
  return (
    <details className="disclosure">
      <summary>Предложения и настройки сохранённого снимка</summary>
      <div className="disclosure-content">
        <p>
          <strong>Вопрос:</strong> {record.scenario.question}
        </p>
        <p>{record.scenario.description}</p>
        <div className="saved-offers">
          {Object.entries(record.scenario.variants).map(([v, text]) => (
            <div key={v} className={"variant-" + v}>
              <b>Предложение {v}</b>
              <p>{text}</p>
            </div>
          ))}
        </div>
        <p className="help">
          Seed {record.seed} · {record.model} · {record.elapsed_seconds} с · ID{" "}
          {record.id}
        </p>
      </div>
    </details>
  );
}
