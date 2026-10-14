import { Notice, percent } from "../../components";
import { COLORS, type ReportItem } from "../../types";
export default function ConversionChart({
  report,
}: {
  report: Record<string, ReportItem>;
}) {
  const rows = Object.entries(report);
  if (!rows.some(([, r]) => r.n))
    return (
      <Notice kind="error">
        Нет валидных ответов для выбранной аудитории.
      </Notice>
    );
  const width = 640,
    height = rows.length * 64 + 34,
    start = 94,
    scale = 455;
  return (
    <svg
      className="conversion-chart"
      viewBox={"0 0 " + width + " " + height}
      role="img"
      aria-label="Доля согласий и 95-процентные интервалы симуляции"
    >
      <title>
        {rows
          .map(
            ([v, r]) =>
              "Вариант " + v + ": " + percent(r.n ? r.conversion : null),
          )
          .join("; ")}
      </title>
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line
            x1={start + t * scale}
            x2={start + t * scale}
            y1={4}
            y2={height - 28}
            className="chart-grid"
          />
          <text
            x={start + t * scale}
            y={height - 7}
            textAnchor="middle"
            className="axis-label"
          >
            {t * 100}%
          </text>
        </g>
      ))}
      {rows.map(([v, r], i) => {
        const y = i * 64 + 25,
          rate = r.n ? r.conversion : null;
        return (
          <g key={v}>
            <text x={0} y={y + 5} className="chart-label">
              Вариант {v}
            </text>
            {rate !== null ? (
              <>
                <rect
                  x={start}
                  y={y - 16}
                  width={Math.max(1, rate * scale)}
                  height={32}
                  rx={5}
                  fill={COLORS[i]}
                />
                <line
                  x1={start + r.confidence_interval[0] * scale}
                  x2={start + r.confidence_interval[1] * scale}
                  y1={y}
                  y2={y}
                  className="interval"
                />
                <text
                  x={Math.min(
                    width - 48,
                    start + r.confidence_interval[1] * scale + 9,
                  )}
                  y={y + 5}
                  className="chart-value"
                >
                  {percent(rate, 0)}
                </text>
              </>
            ) : (
              <text x={start} y={y + 5} className="axis-label">
                Нет ответов
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
