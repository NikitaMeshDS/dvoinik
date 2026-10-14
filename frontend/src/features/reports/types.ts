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
};
export type ExportKind =
  "record" | "validation" | "survey-template" | "preview";
export type ExportAction = (
  format: "json" | "csv",
  kind?: ExportKind,
  preview_id?: string,
) => void;
