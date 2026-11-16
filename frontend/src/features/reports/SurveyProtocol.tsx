import type { SurveyProtocol } from "../../types";
const ASSIGNMENTS = {
  unknown: "Не указано",
  random_one: "Случайно: один человек — одно предложение",
  one_nonrandom: "Одно предложение без случайного распределения",
  all_variants: "Каждый участник оценивал все предложения",
};
export function ProtocolSummary({ protocol }: { protocol?: SurveyProtocol }) {
  if (!protocol || !Object.values(protocol).some((v) => v && v !== "unknown"))
    return (
      <p className="help">
        Сведения о сборе ответов не сохранены. Источник, период и распределение
        предложений неизвестны.
      </p>
    );
  return (
    <section
      className="survey-protocol-summary"
      aria-label="Сведения о сборе ответов"
    >
      <h3>Как собраны ответы</h3>
      <dl>
        <dt>Способ набора</dt>
        <dd>{protocol.recruitment || "Не указан"}</dd>
        <dt>Период сбора</dt>
        <dd>
          {protocol.collected_from || "Начало не указано"} —{" "}
          {protocol.collected_to || "Окончание не указано"}
        </dd>
        <dt>Распределение предложений</dt>
        <dd>{ASSIGNMENTS[protocol.assignment ?? "unknown"]}</dd>
        {protocol.notes && (
          <>
            <dt>Примечание исследователя</dt>
            <dd>{protocol.notes}</dd>
          </>
        )}
      </dl>
      <p className="help">
        Сведения предоставлены пользователем. Приложение не проверяет их
        достоверность и уникальность участников.
      </p>
    </section>
  );
}
export default function ProtocolEditor({
  value,
  onChange,
  disabled,
}: {
  value: SurveyProtocol;
  onChange: (value: SurveyProtocol) => void;
  disabled: boolean;
}) {
  const patch = (field: keyof SurveyProtocol, text: string) => {
    const next = { ...value };
    if (text && text !== "unknown") Object.assign(next, { [field]: text });
    else delete next[field];
    onChange(next);
  };
  return (
    <details className="disclosure survey-protocol">
      <summary>Как собраны ответы</summary>
      <div className="disclosure-content">
        <p className="help">
          Необязательные сведения для этой загрузки. Укажите способ набора и
          условия исследования без имён, контактов и других персональных данных.
          Неизвестные поля оставьте пустыми.
        </p>
        <div className="question-fields">
          <label className="field">
            <span>Способ набора участников</span>
            <input
              maxLength={1000}
              value={value.recruitment ?? ""}
              disabled={disabled}
              onChange={(e) => patch("recruitment", e.target.value)}
            />
          </label>
          <label className="field">
            <span>Распределение предложений</span>
            <select
              aria-label="Распределение предложений"
              value={value.assignment ?? "unknown"}
              disabled={disabled}
              onChange={(e) => patch("assignment", e.target.value)}
            >
              {Object.entries(ASSIGNMENTS).map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Начало сбора ответов</span>
            <input
              type="date"
              value={value.collected_from ?? ""}
              disabled={disabled}
              onChange={(e) => patch("collected_from", e.target.value)}
            />
          </label>
          <label className="field">
            <span>Окончание сбора ответов</span>
            <input
              type="date"
              value={value.collected_to ?? ""}
              disabled={disabled}
              onChange={(e) => patch("collected_to", e.target.value)}
            />
          </label>
        </div>
        <label className="field">
          <span>Примечание к исследованию</span>
          <textarea
            maxLength={1000}
            value={value.notes ?? ""}
            disabled={disabled}
            onChange={(e) => patch("notes", e.target.value)}
          />
        </label>
        <button
          className="text-link"
          disabled={disabled}
          onClick={() => onChange({})}
        >
          Очистить сведения о сборе
        </button>
        <p className="help">
          Заполните до выбора CSV. Для изменения сведений после загрузки
          отмените предпросмотр и выберите файл заново.
        </p>
      </div>
    </details>
  );
}
