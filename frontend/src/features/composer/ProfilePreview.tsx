import { useState } from "react";
import { UserRound } from "lucide-react";
import type { Catalog } from "../../types";
import type { AudiencePreview } from "./useLaunchPreview";

export default function ProfilePreview({
  catalog,
  preview,
  loading,
  error,
  mock,
  deposit,
}: {
  catalog: Catalog;
  preview: AudiencePreview | null;
  loading: boolean;
  error: string;
  mock: boolean;
  deposit: boolean;
}) {
  const [selected, setSelected] = useState("");
  const [selectedOffer, setSelectedOffer] = useState("");
  const options = Object.keys(preview?.counts ?? {}).filter(
    (id) => preview && preview.counts[id] > 0,
  );
  const segment = options.includes(selected) ? selected : (options[0] ?? "");
  const profile = preview?.profiles?.[segment];
  const sources = catalog.sources?.segments[segment] ?? [];
  const offerPrompts = profile?.offer_prompts ?? {};
  const offers = Object.keys(offerPrompts);
  const offer = offers.includes(selectedOffer) ? selectedOffer : offers[0];

  return (
    <details className="disclosure profile-preview">
      <summary>
        <UserRound size={16} aria-hidden="true" />
        Что увидит двойник
      </summary>
      <div className="disclosure-content">
        <p>
          {mock
            ? "В демо ответ рассчитывается по сегменту и тексту предложения. Анкеты видны в отчёте, а запросы к модели не отправляются."
            : "В отдельный запрос для каждого предложения входят анкета, текст этого предложения, вопрос и категории отказа. Анкета сохраняется при переходе к следующему предложению."}
        </p>
        {loading || !preview ? (
          <p role="status">
            {error ||
              (loading
                ? "Готовим анкеты…"
                : "Выберите сегмент, чтобы увидеть анкету.")}
          </p>
        ) : (
          <>
            <label className="field profile-preview-segment">
              <span>Сегмент для примера</span>
              <select
                value={segment}
                onChange={(event) => setSelected(event.target.value)}
              >
                {options.map((id) => (
                  <option key={id} value={id}>
                    {catalog.segments[id]?.name ?? id}
                  </option>
                ))}
              </select>
            </label>
            {profile ? (
              <div className="profile-preview-example">
                <strong>
                  {mock
                    ? "Пример анкеты из этой симуляции"
                    : "Текст анкеты в запросе"}
                </strong>
                <p>{profile.text}</p>
                {profile.available_deposit_rub !== undefined && (
                  <p className="help">
                    Синтетическая сумма для проверки взноса —{" "}
                    {profile.available_deposit_rub.toLocaleString("ru-RU")} ₽.
                    Она используется в расчёте доступности внутри приложения.
                  </p>
                )}
              </div>
            ) : (
              <p>
                Пример анкеты доступен в локальной версии с корректным seed.
              </p>
            )}
            {offer && preview.respondent_system && (
              <details className="disclosure profile-preview-request">
                <summary>Текст запроса к модели</summary>
                <div className="disclosure-content">
                  {mock && (
                    <p>
                      Пример для режима LLM. Демо выполняется без вызова модели.
                    </p>
                  )}
                  <label className="field profile-preview-segment">
                    <span>Предложение в запросе</span>
                    <select
                      value={offer}
                      onChange={(event) => setSelectedOffer(event.target.value)}
                    >
                      {offers.map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <pre
                    className="profile-preview-message"
                    aria-label="Сообщение с анкетой и предложением"
                  >
                    {offerPrompts[offer]}
                  </pre>
                  <details className="disclosure profile-preview-instruction">
                    <summary>Инструкция модели</summary>
                    <pre className="profile-preview-message">
                      {preview.respondent_system}
                    </pre>
                  </details>
                </div>
              </details>
            )}
            {deposit && segment === "senior" && (
              <p>
                Для вклада анкета сохраняет цифровой навык и исключает готовую
                установку «предпочитает отделение».
              </p>
            )}
            <p>
              Имя, возраст, город, доход, привычки и установки выбираются из
              справочника сегмента. Это синтетические значения.
            </p>
            {sources.length > 0 && (
              <ul className="profile-preview-sources">
                {sources.map(({ fact, use, source, url }) => (
                  <li key={fact}>
                    <strong>{fact}.</strong> {use}{" "}
                    <a href={url} target="_blank" rel="noreferrer">
                      {source}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </details>
  );
}
