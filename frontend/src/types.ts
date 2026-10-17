export type Scenario = {
  title: string;
  description: string;
  question: string;
  variants: Record<string, string>;
  population: Record<string, number>;
  objections: string[];
  origin?: Origin;
};
export type Origin = {
  kind: "iteration" | "hypothesis";
  record_id: string;
  title: string;
  lever?: string;
  change?: string;
  variant?: string;
};
export type Segment = {
  name: string;
  age: [number, number];
  region: string[];
  income: string[];
  habits: string[];
  attitude: string[];
};
export type SegmentSource = {
  fact: string;
  use: string;
  status: string;
  source: string;
  date: string;
  url: string;
};
export type Catalog = {
  scenarios: Record<string, Scenario>;
  segments: Record<string, Segment>;
  sources?: { segments: Record<string, SegmentSource[]>; gaps: string };
  risks?: { segments: Record<string, string>; source: string };
};
export type User = {
  id: string;
  username: string;
  name: string;
  role: "admin" | "analyst" | "demo";
};
export type Session = {
  user: User;
  csrf_token: string;
  default_mock?: boolean;
  mode: string;
  model: string;
};
export type Quote = {
  decision: boolean;
  quote: string;
  who: string;
  segment: string;
  segment_id: string;
};
export type Cell = {
  n: number;
  yes: number;
  conversion: number | null;
  name?: string;
  objections?: Record<string, number>;
};
export type ReportItem = {
  n: number;
  yes: number;
  conversion: number | null;
  requested_n: number;
  failed_n: number;
  confidence_interval: [number, number];
  segments: Record<string, Cell>;
  objections: Record<string, number>;
  quotes: Quote[];
  failure_examples?: string[];
  probability?: { mean: number; sd: number; n: number };
  likert?: number[];
};
export type Profile = {
  id: number;
  segment: string;
  name: string;
  age: number;
  region: string;
  income: string;
  habits: string[];
  attitude: string;
};
export type ValidationCell = {
  variant: string;
  segment: string;
  survey_n: number;
  actual: number;
  predicted: number;
  error: number;
};
export type ValidationResult = {
  mae_conversion: number;
  spearman_variants: number | null;
  winner_match: boolean | null;
  survey_n: number;
  matched_cells: number;
  cells: ValidationCell[];
  actual_winners: string[];
  predicted_winners: string[];
  baseline?: {
    twins_mae_variants: number;
    baseline_mae_variants: number;
    twins_spearman: number | null;
    baseline_spearman: number | null;
    baseline_winner_match: boolean | null;
    variants: {
      variant: string;
      actual: number;
      twins: number;
      baseline: number;
    }[];
  };
};
export type Validation = {
  created_at: string;
  cells: { variant: string; segment: string; n: number; yes: number }[];
  result: ValidationResult;
  source?: string;
};
export type Experiment = {
  schema_version: number;
  id: string;
  created_at: string;
  scenario_key: string;
  scenario: Scenario;
  n: number;
  mock: boolean;
  seed: number;
  model: string;
  elapsed_seconds: number;
  sample: boolean;
  report: Record<string, ReportItem>;
  population_counts: Record<string, number>;
  population_sample: Profile[];
  signature: string;
  validation?: Validation;
  import_origin_id?: string;
  baseline?: {
    method: string;
    rates?: Record<string, number>;
    error?: string;
  };
};
export type Estimate = {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  minutes: number;
  latency_s: number;
  concurrency: number;
  cost: number | null;
  currency: string | null;
  detail: string;
};
export type Draft = {
  origin?: Origin;
  key: string;
  title: string;
  description: string;
  question: string;
  variants: Record<string, string>;
  variantCount: number;
  weights: Record<string, number>;
  objections: string[];
  n: number;
  mock: boolean;
  seed: number;
  concurrency: number;
};
export type RunPayload = {
  scenario_key: string;
  scenario: Scenario;
  n: number;
  mock: boolean;
  seed: number;
  concurrency: number;
};
export type Job = {
  id: string;
  status:
    "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";
  done: number;
  total: number;
  record?: Experiment | null;
  error?: string | null;
  saved?: boolean;
};
export type ComparisonRow = {
  variant: string;
  segment?: string;
  left: number | null;
  right: number | null;
  left_n: number | null;
  right_n: number | null;
  delta_pp: number | null;
};
export type Comparison = {
  left: Experiment;
  right: Experiment;
  comparison: {
    changes: {
      field: string;
      label: string;
      before: unknown;
      after: unknown;
    }[];
    variants: ComparisonRow[];
    segments: ComparisonRow[];
  };
};
export const VARIANTS = ["A", "B", "C", "D", "E"];
export const TITLES: Record<string, string> = {
  student_card: "Студенческая карта",
  family_budget: "Семейный счёт",
  credit_card: "Кредитная карта",
  senior_deposit: "Вклад для пенсионеров",
  push_cashback: "Пуш о кэшбэке",
  self_employed: "Тариф для самозанятых",
  nonresident_transfer: "Переводы для нерезидентов",
  custom: "Свой сценарий",
};
export const COLORS = ["#2457d6", "#137d76", "#7d65b4", "#b27a30", "#b65c84"];
