import type { ReportItem } from "../../types";
export type Insights = {
  report: Record<string, ReportItem>;
  summary: {
    leaders: string[];
    gap_pp: number;
    best: number;
    failed_n: number;
  };
  quality: { kind: string; title: string; detail: string };
  stability: Stability | null;
  plan?: LivePlan;
  baseline?: BaselineAgreement | null;
  hypotheses?: Hypotheses;
};
export type Hypothesis = {
  id: string;
  kind: "objection" | "segment_offer";
  lever_id: string;
  lever: string;
  change: string;
  variant: string;
  alternative?: string;
  segments: string[];
  segment_names: string[];
  objections: string[];
  evidence: string[];
  base_rate: number;
  ceiling_pp: number;
  audience_pp: number;
  check_n: number | null;
  base_text: string;
  proposal: string;
  removed: string[];
  added: string[];
};
export type Hypotheses = { leader: string | null; items: Hypothesis[] };
export type Stability = {
  leader: string;
  runner_up: string;
  share: number;
  level: "stable" | "moderate" | "unstable";
  label: string;
  draws: number;
  detail: string;
};
export type LivePlan = {
  comparisons: {
    pair: [string, string];
    rates: [number, number];
    gap_pp: number;
    n_per_variant: number | null;
  }[];
  exploratory_n: number;
  exploratory_detectable_pp: number;
  focus_segments: {
    segment: string;
    name: string;
    leader: string;
    gap_pp: number;
  }[];
  questions: { text: string; source: string }[];
  assumptions: string;
};
export type BaselineAgreement = {
  method: "single_prompt" | "demo_rule";
  error?: string;
  rows?: { variant: string; twins: number; baseline: number }[];
  same_leader?: boolean;
  twin_leaders?: string[];
  baseline_leaders?: string[];
  spearman?: number | null;
};
export type ExportKind =
  "record" | "validation" | "survey-template" | "preview" | "summary";
export type ExportAction = (
  format: "json" | "csv" | "html",
  kind?: ExportKind,
  preview_id?: string,
) => void;
