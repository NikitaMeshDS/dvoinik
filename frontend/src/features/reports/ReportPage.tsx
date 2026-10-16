import { useState } from "react";
import { download } from "../../api";
import { Notice, Button } from "../../components";
import type { Catalog, Experiment } from "../../types";
import type { ExportAction } from "./types";
import { useInsights } from "./useInsights";
import ReportHeader from "./ReportHeader";
import ReportTabs, { type ReportTab } from "./ReportTabs";
import Overview from "./Overview";
import Audience from "./Audience";
import Voices from "./Voices";
import ValidationPanel from "./ValidationPanel";
export default function ReportPage({
  record,
  catalog,
  onBack,
  onReuse,
  onUpdated,
  onCompare,
  onError,
  pending,
  onRetry,
}: {
  record: Experiment;
  catalog: Catalog;
  onBack: () => void;
  onReuse: () => void;
  onUpdated: (record: Experiment) => void;
  onCompare: () => void;
  onError: (error: unknown) => void;
  pending?: string;
  onRetry?: () => void;
}) {
  const [tab, setTab] = useState<ReportTab>("overview"),
    [segment, setSegment] = useState("all"),
    [variant, setVariant] = useState(Object.keys(record.report)[0]),
    [decision, setDecision] = useState("all");
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
        onBack={onBack}
        onReuse={onReuse}
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
        <div hidden={tab !== "validation"}>
          <ValidationPanel
            record={record}
            catalog={catalog}
            onUpdated={onUpdated}
            onExport={exportFile}
            plan={insights.base?.plan}
          />
        </div>
      </section>
    </>
  );
}
