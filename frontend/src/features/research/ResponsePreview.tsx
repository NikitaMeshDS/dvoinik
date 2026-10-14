import { percent } from "../../components";
import { COLORS, type ReportItem } from "../../types";
/** Small multiples use a common0–100% scale, never a stacked distribution. */
export default function ResponsePreview({
  report,
}: {
  report: Record<string, ReportItem>;
}) {
  const entries = Object.entries(report),
    valid = entries.filter(([, r]) => r.n > 0 && r.conversion !== null);
  const best = valid.length
    ? Math.max(...valid.map(([, r]) => r.conversion!))
    : null;
  const description = entries
    .map(([id, r]) => id + ": " + percent(r.n ? r.conversion : null))
    .join(", ");
  return (
    <span
      className="response-preview"
      role="img"
      aria-label={"Доли согласий: " + description}
    >
      {entries.map(([id, r], i) => {
        const rate = r.n ? r.conversion : null,
          leader =
            rate !== null && best !== null && Math.abs(rate - best) < 1e-9;
        return (
          <span
            className={"response-mini " + (leader ? "is-leader" : "")}
            key={id}
            aria-hidden="true"
          >
            <span>
              <b>{id}</b>
              <small>{percent(rate, 0)}</small>
            </span>
            <span className="response-mini-track">
              <i
                style={{
                  width: (rate ?? 0) * 100 + "%",
                  background: COLORS[i],
                }}
              />
            </span>
          </span>
        );
      })}
    </span>
  );
}
