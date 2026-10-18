import { useState } from "react";
import { Download, FileText, FileSpreadsheet, BookOpen } from "lucide-react";
import { download, ignored, message } from "../../api";
import { Button, Notice } from "../../components";
import type { Catalog, Experiment } from "../../types";

export default function SurveyPreparation({
  record,
  catalog,
}: {
  record: Experiment;
  catalog: Catalog;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const variants = Object.entries(record.scenario.variants);
  const segments = Object.keys(record.scenario.population);
  const missing = variants.flatMap(([vid]) =>
    segments
      .filter((sid) => !record.report[vid]?.segments[sid]?.n)
      .map((sid) => `${sid}/${vid}`),
  );
  const covered = variants.length * segments.length - missing.length;
  const exportKit = async () => {
    setBusy(true);
    setError("");
    try {
      await download("/export", {
        record_id: record.id,
        kind: "survey-kit",
        format: "zip",
      });
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section
      className="survey-preparation"
      aria-label="Подготовка живого опроса"
    >
      <div className="survey-preparation-heading">
        <div>
          <h2>
            <span className="validation-step" aria-hidden="true">
              2
            </span>{" "}
            Подготовьте живой опрос
          </h2>
          <p>
            Готовые материалы по этому снимку: тот же вопрос и те же условия,
            без результатов симуляции для респондентов.
          </p>
        </div>
        <Button kind="primary" disabled={busy || !covered} onClick={exportKit}>
          <Download size={17} />
          {busy ? "Готовим комплект…" : "Скачать комплект опроса"}
        </Button>
      </div>
      <ul className="survey-kit-files" aria-label="Файлы в комплекте ZIP">
        <li>
          <FileText size={21} />
          <div>
            <strong>Анкета</strong>
            <span>HTML для браузера и печати</span>
          </div>
        </li>
        <li>
          <FileSpreadsheet size={21} />
          <div>
            <strong>Шаблон ответов</strong>
            <span>CSV с пустыми решениями</span>
          </div>
        </li>
        <li>
          <BookOpen size={21} />
          <div>
            <strong>Инструкция</strong>
            <span>Коды и порядок сбора ответов</span>
          </div>
        </li>
      </ul>
      {!covered ? (
        <Notice>
          Нет валидных ответов симуляции для сопоставления. Повторите
          исследование перед подготовкой проверки.
        </Notice>
      ) : missing.length > 0 ? (
        <Notice>
          Для {missing.length} пар «вариант — сегмент» нет валидных ответов
          симуляции. Они исключены из шаблона. Для проверки всей аудитории
          повторите запуск с нужным покрытием.
        </Notice>
      ) : null}
      {error && <Notice kind="error">{error}</Notice>}
      <details className="survey-preview">
        <summary>Посмотреть анкету и коды сегментов</summary>
        <div className="survey-preview-content">
          <div className="survey-questionnaire">
            <h3>Вопрос для каждого предложения</h3>
            <p className="survey-question">{record.scenario.question}</p>
            <p className="help">
              Ответ: да или нет. Причину можно записать отдельно; в метрики CSV
              входят только решения.
            </p>
            {variants.map(([vid, text]) => (
              <div className="survey-offer" key={vid}>
                <span className="survey-variant">{vid}</span>
                <p>{text}</p>
              </div>
            ))}
          </div>
          <div className="survey-segment-key">
            <h3>Коды для исследователя</h3>
            <p className="help">
              Отнесите респондента к сегменту по заранее согласованным критериям
              набора.
            </p>
            <dl>
              {segments.map((sid) => (
                <div key={sid}>
                  <dt>{catalog.segments[sid]?.name ?? sid}</dt>
                  <dd>
                    <code>{sid}</code>
                  </dd>
                </div>
              ))}
            </dl>
            {missing.length > 0 && (
              <p className="help">Без сопоставления: {missing.join(", ")}</p>
            )}
          </div>
        </div>
      </details>
    </section>
  );
}
