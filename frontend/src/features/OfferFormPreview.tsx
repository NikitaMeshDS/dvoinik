import { useState } from "react";

export default function OfferFormPreview({
  offers,
  question,
  minimum,
}: {
  offers: [string, string][];
  question: string;
  minimum?: number;
}) {
  const [selected, setSelected] = useState(offers[0]?.[0]);
  const offer = offers.find(([variant]) => variant === selected) ?? offers[0];
  if (!offer) return null;

  return (
    <>
      <div
        className="offer-form-picker"
        role="group"
        aria-label="Бланк для просмотра"
      >
        {offers.map(([variant]) => (
          <button
            key={variant}
            type="button"
            aria-pressed={variant === offer[0]}
            onClick={() => setSelected(variant)}
          >
            Вариант {variant}
          </button>
        ))}
      </div>
      <section className="offer-form-paper" aria-label="Бланк участника">
        <p>{offer[1].trim() || "Добавьте текст предложения"}</p>
        {minimum !== undefined && minimum > 0 && (
          <p>Минимальный взнос — {minimum.toLocaleString("ru-RU")} ₽.</p>
        )}
        <h3>{question.trim() || "Добавьте вопрос исследования"}</h3>
        <div className="offer-form-answers">
          <span>
            <span aria-hidden="true">☐</span> Да
          </span>
          <span>
            <span aria-hidden="true">☐</span> Нет
          </span>
        </div>
      </section>
    </>
  );
}
