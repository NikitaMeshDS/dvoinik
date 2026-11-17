import { Eye } from "lucide-react";
import { VARIANTS, type Draft } from "../../types";
export default function RespondentPreview({ draft }: { draft: Draft }) {
  return (
    <details className="respondent-preview">
      <summary>
        <Eye size={18} aria-hidden="true" />
        Как выглядит вопрос для участника
      </summary>
      <section aria-label="Предпросмотр вопроса">
        <p className="help">
          Макет формулировок из текущего черновика. Каждое предложение
          оценивается отдельно; порядок и распределение участников определяет
          исследователь.
        </p>
        <h3>{draft.question.trim() || "Добавьте вопрос исследования"}</h3>
        <div className="respondent-offers">
          {VARIANTS.slice(0, draft.variantCount).map((v) => (
            <article key={v}>
              <span className="respondent-letter">{v}</span>
              <p>{draft.variants[v]?.trim() || "Добавьте текст предложения"}</p>
              <span className="respondent-answer">Ответ: да или нет</span>
            </article>
          ))}
        </div>
        <p className="help">
          Это предпросмотр, ответы здесь не собираются. Анкету для живой
          проверки можно скачать после сохранения исследования.
        </p>
      </section>
    </details>
  );
}
