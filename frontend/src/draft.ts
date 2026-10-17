import {
  VARIANTS,
  type Draft,
  type Experiment,
  type Scenario,
  type RunPayload,
} from "./types";
export function draftFromScenario(
  s: Scenario,
  key: string,
  mock = true,
): Draft {
  return {
    key,
    title: s.title,
    description: s.description,
    question: s.question,
    variants: { ...s.variants },
    variantCount: Object.keys(s.variants).length,
    weights: Object.fromEntries(
      Object.entries(s.population).map(([k, v]) => [k, v * 100]),
    ),
    objections: [...s.objections],
    n: 200,
    mock,
    seed: 42,
    concurrency: 16,
  };
}
export function draftFromRecord(record: Experiment, demo = false): Draft {
  return {
    ...draftFromScenario(record.scenario, "custom"),
    origin: {
      kind: "iteration",
      record_id: record.id,
      title: record.scenario.title,
    },
    n: record.n,
    mock: demo ? true : record.mock,
    seed: record.seed,
  };
}
/** Черновик A/B-проверки гипотезы: лидер против нового текста на затронутых сегментах. */
export function draftFromHypothesis(
  record: Experiment,
  hypothesis: {
    lever: string;
    change: string;
    variant: string;
    base_text: string;
    segments: string[];
  },
  proposal: string,
  demo = false,
): Draft {
  const base = draftFromRecord(record, demo);
  const segments = hypothesis.segments.filter(
    (sid) => (record.scenario.population[sid] ?? 0) > 0,
  );
  return {
    ...base,
    origin: {
      kind: "hypothesis",
      record_id: record.id,
      title: record.scenario.title,
      lever: hypothesis.lever,
      change: hypothesis.change.slice(0, 300),
      variant: hypothesis.variant,
    },
    title: (
      record.scenario.title +
      " · гипотеза «" +
      hypothesis.lever +
      "»"
    ).slice(0, 200),
    description: (
      "Проверка гипотезы «" +
      hypothesis.lever +
      "»: A — текущий вариант " +
      hypothesis.variant +
      ", B — " +
      hypothesis.change.charAt(0).toLowerCase() +
      hypothesis.change.slice(1) +
      ". " +
      record.scenario.description
    ).slice(0, 4000),
    variants: { A: hypothesis.base_text, B: proposal },
    variantCount: 2,
    weights: segments.length
      ? Object.fromEntries(
          segments.map((sid) => [sid, record.scenario.population[sid] * 100]),
        )
      : base.weights,
  };
}
export function runPayload(d: Draft): RunPayload {
  return {
    scenario_key: d.key,
    scenario: {
      title: d.title.trim(),
      description: d.description.trim(),
      question: d.question.trim(),
      variants: Object.fromEntries(
        VARIANTS.slice(0, d.variantCount).map((v) => [
          v,
          (d.variants[v] ?? "").trim(),
        ]),
      ),
      population: Object.fromEntries(
        Object.entries(d.weights).filter(([, n]) => n > 0),
      ),
      objections: d.objections.map((s) => s.trim()).filter(Boolean),
      ...(d.origin ? { origin: d.origin } : {}),
    },
    n: d.n,
    mock: d.mock,
    seed: d.seed,
    concurrency: d.concurrency,
  };
}
export function draftError(d: Draft): string | null {
  if (!d.title.trim()) return "Добавьте название исследования.";
  if (!d.question.trim()) return "Добавьте вопрос двойникам.";
  for (const v of VARIANTS.slice(0, d.variantCount))
    if (!(d.variants[v] ?? "").trim())
      return "Заполните предложение " + v + ".";
  if (!Object.values(d.weights).some((n) => n > 0))
    return "Выберите хотя бы один сегмент аудитории.";
  if (!d.objections.some((s) => s.trim()))
    return "Добавьте хотя бы одну категорию отказа.";
  if (!Number.isInteger(d.n) || d.n < 1 || d.n > 10000)
    return "Размер аудитории: целое число от 1 до 10 000.";
  if (!Number.isInteger(d.seed) || d.seed < 0 || d.seed > 999999)
    return "Seed: целое число от 0 до 999 999.";
  if (
    !Number.isInteger(d.concurrency) ||
    d.concurrency < 1 ||
    d.concurrency > 64
  )
    return "Параллельность: от 1 до 64 запросов.";
  return null;
}
