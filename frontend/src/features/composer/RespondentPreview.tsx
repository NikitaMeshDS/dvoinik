import { Eye } from "lucide-react";
import { VARIANTS, type Draft } from "../../types";
import OfferFormPreview from "../OfferFormPreview";
export default function RespondentPreview({ draft }: { draft: Draft }) {
  return (
    <details className="respondent-preview">
      <summary>
        <Eye size={18} aria-hidden="true" />
        Как выглядит вопрос для участника
      </summary>
      <section aria-label="Предпросмотр вопроса">
        <p className="help">
          Здесь можно сверить бланк из черновика. Ответы в предпросмотре не
          сохраняются.
        </p>
        <OfferFormPreview
          key={draft.key}
          offers={VARIANTS.slice(0, draft.variantCount).map((v) => [
            v,
            draft.variants[v] ?? "",
          ])}
          question={draft.question}
          minimum={draft.depositMinimumRub}
        />
      </section>
    </details>
  );
}
