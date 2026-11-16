import type { Experiment } from "../../types";
import type { Hypothesis } from "./types";

export function sameHypothesisSetup(
  parent: Experiment,
  hypothesis: Hypothesis,
  child: Experiment,
) {
  if (child.scenario.variants.A?.trim() !== hypothesis.base_text.trim())
    return false;
  const wanted = hypothesis.segments.filter(
    (s) => (parent.scenario.population[s] ?? 0) > 0,
  );
  const expected = wanted.length
    ? Object.fromEntries(wanted.map((s) => [s, parent.scenario.population[s]]))
    : parent.scenario.population;
  const actual = child.scenario.population;
  const keys = Object.keys(expected).filter((s) => expected[s] > 0),
    other = Object.keys(actual).filter((s) => actual[s] > 0);
  const sum = keys.reduce((n, s) => n + expected[s], 0),
    total = other.reduce((n, s) => n + actual[s], 0);
  return (
    sum > 0 &&
    total > 0 &&
    keys.length === other.length &&
    keys.every(
      (s) => Math.abs(expected[s] / sum - (actual[s] ?? 0) / total) < 1e-9,
    )
  );
}
export function hypothesisChecks(
  parent: Experiment,
  hypothesis: Hypothesis,
  checks: Experiment[],
) {
  return checks
    .filter((child) => {
      const origin = child.scenario.origin;
      if (origin?.kind !== "hypothesis" || origin.record_id !== parent.id)
        return false;
      if (origin.hypothesis_id)
        return (
          !!hypothesis.stable_id &&
          origin.hypothesis_id === hypothesis.stable_id
        );
      return (
        origin.variant === hypothesis.variant &&
        origin.lever === hypothesis.lever &&
        origin.change === hypothesis.change.slice(0, 300) &&
        sameHypothesisSetup(parent, hypothesis, child)
      );
    })
    .sort(
      (a, b) =>
        b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id),
    );
}
