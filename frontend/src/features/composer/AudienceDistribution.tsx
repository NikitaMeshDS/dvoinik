import { percent } from "../../components";
import type { Catalog } from "../../types";
export default function AudienceDistribution({
  preview,
  segments,
  error = "",
}: {
  preview?: { shares: Record<string, number>; counts: Record<string, number> };
  segments: Catalog["segments"];
  error?: string;
}) {
  const rows = Object.entries(preview?.shares ?? {}).filter(
    ([, share]) => share > 0,
  );
  return (
    <section
      className="audience-distribution"
      aria-label="Состав синтетической аудитории"
      aria-busy={!preview && !error}
    >
      <h3>Состав синтетической аудитории</h3>
      {!preview ? (
        <p className="help" role={error ? undefined : "status"}>
          {error
            ? "Распределение недоступно. Проверьте сообщение ниже и измените параметры аудитории."
            : "Распределение появится после расчёта текущих параметров."}
        </p>
      ) : (
        <>
          <ul>
            {rows.map(([sid, share]) => (
              <li key={sid}>
                <div>
                  <strong>{segments[sid]?.name ?? sid}</strong>
                  <span>
                    {percent(share)} ·{" "}
                    {(preview.counts[sid] ?? 0).toLocaleString("ru-RU")}{" "}
                    профилей
                  </span>
                </div>
                <span className="audience-share-track" aria-hidden="true">
                  <i style={{ width: share * 100 + "%" }} />
                </span>
              </li>
            ))}
          </ul>
          <p className="help">
            Доли нормированы к 100%. Число профилей округлено движком. Это
            состав симуляции, а не подтверждённая выборка клиентов.
          </p>
        </>
      )}
    </section>
  );
}
