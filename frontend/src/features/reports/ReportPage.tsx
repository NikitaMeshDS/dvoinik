import { useState } from "react";
import { download } from "../../api";
import { Notice, Button } from "../../components";
import type { Catalog, Experiment } from "../../types";
import type { ExportAction, Hypothesis } from "./types";
import { useInsights } from "./useInsights";
import { useUnsavedSurvey } from "./useUnsavedSurvey";
import ReportHeader from "./ReportHeader";
import ReportTabs, { type ReportTab } from "./ReportTabs";
import Overview from "./Overview";
import Audience from "./Audience";
import Voices from "./Voices";
import ValidationPanel from "./ValidationPanel";
import Hypotheses from "./Hypotheses";
import OriginBanner from "./OriginBanner";
function leaderOf(record: Experiment) {
  const entries = Object.entries(record.report).filter(([, r]) => r.n);
  if (!entries.length) return Object.keys(record.report)[0];
  return entries.reduce((best, item) =>
    (item[1].conversion ?? 0) > (best[1].conversion ?? 0) ? item : best,
  )[0];
}
export default function ReportPage({
  record,
  initialTab = "overview",
  selectedTab,
  onTabChange,
  catalog,
  onBack,
  onReuse,
  onTestHypothesis,
  onOpenRecord,
  onCompareWith,
  related = [],
  onUpdated,
  onCompare,
  onError,
  pending,
  onRetry,
}: {
  record: Experiment;
  initialTab?: ReportTab;
  selectedTab?: ReportTab;
  onTabChange?: (tab: ReportTab) => void;
  catalog: Catalog;
  onBack: () => void;
  onReuse: () => void;
  onTestHypothesis?: (hypothesis: Hypothesis, proposal: string) => void;
  onOpenRecord?: (id: string) => void;
  onCompareWith?: (id: string) => void;
  related?: Experiment[];
  onUpdated: (record: Experiment) => void;
  onCompare: () => void;
  onError: (error: unknown) => void;
  pending?: string;
  onRetry?: () => void;
}) {
  const [localTab, setLocalTab] = useState<ReportTab>(initialTab),
    [segment, setSegment] = useState("all"),
    [variant, setVariant] = useState(() => leaderOf(record)),
    [decision, setDecision] = useState("all");
  const [surveyDirty, setSurveyDirty] = useState(false);
  const leave = useUnsavedSurvey(record.id, surveyDirty);
  const openRecord = onOpenRecord
    ? (id: string) => leave(() => onOpenRecord(id))
    : undefined;
  const testHypothesis = onTestHypothesis
    ? (hypothesis: Hypothesis, proposal: string) =>
        leave(() => onTestHypothesis(hypothesis, proposal))
    : undefined;
  const tab = selectedTab ?? localTab;
  const setTab = (value: ReportTab) => {
    setLocalTab(value);
    onTabChange?.(value);
  };
  const insights = useInsights(record, segment);
  const exportFile: ExportAction = (format, kind = "record", preview_id) => {
    void download("/export", {
      record_id: record.id,
      format,
      kind,
      ...(preview_id ? { preview_id } : {}),
    }).catch(onError);
  };
  return (
    <>
      <ReportHeader
        record={record}
        base={insights.base}
        onBack={() => leave(onBack)}
        onReuse={() => leave(onReuse)}
        onCompare={onCompare}
        pending={pending}
        onRetry={onRetry}
        onExport={exportFile}
      />
      {insights.error && (
        <Notice kind="error">
          {insights.error}
          <div>
            <Button onClick={insights.retry}>
              Повторить загрузку аналитики
            </Button>
          </div>
        </Notice>
      )}
      <OriginBanner
        record={record}
        stability={insights.base?.stability}
        plan={insights.base?.plan}
        onOpen={openRecord}
        onValidation={() => setTab("validation")}
        onCompare={onCompareWith}
      />
      <ReportTabs tab={tab} setTab={setTab} />
      <section
        role="tabpanel"
        id={"panel-" + tab}
        aria-labelledby={"tab-" + tab}
      >
        {tab === "overview" && (
          <Overview
            record={record}
            catalog={catalog}
            focus={insights.focus}
            segment={segment}
            setSegment={setSegment}
            variant={variant}
            setVariant={setVariant}
            baseline={insights.base?.baseline}
            plan={insights.base?.plan}
            onPlan={() => setTab("validation")}
            hypothesisCount={insights.base?.hypotheses?.items.length}
            onHypotheses={() => setTab("hypotheses")}
          />
        )}
        {tab === "people" && <Audience record={record} catalog={catalog} />}
        {tab === "voices" && (
          <Voices
            record={record}
            catalog={catalog}
            segment={segment}
            setSegment={setSegment}
            variant={variant}
            setVariant={setVariant}
            decision={decision}
            setDecision={setDecision}
          />
        )}
        {tab === "hypotheses" && (
          <Hypotheses
            record={record}
            data={insights.base?.hypotheses}
            onTest={testHypothesis}
            checks={related.filter(
              (r) => r.scenario.origin?.record_id === record.id,
            )}
            onOpen={openRecord}
          />
        )}
        <div hidden={tab !== "validation"}>
          <ValidationPanel
            record={record}
            catalog={catalog}
            onUpdated={onUpdated}
            onExport={exportFile}
            plan={insights.base?.plan}
            onDirtyChange={setSurveyDirty}
          />
        </div>
      </section>
    </>
  );
}
