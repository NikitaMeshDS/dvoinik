import { useEffect, useState } from "react";
import { api, ApiError, ignored, message } from "../api";
import { draftFromHypothesis, runPayload } from "../draft";
import { comparisonOrder } from "../data";
import { Notice, Button } from "../components";
import { Administration } from "../Account";
import { ImportDialog, ComparisonDialog } from "../Compare";
import Composer from "../Composer";
import Library, { INITIAL_LIBRARY, type LibraryState } from "../Library";
import Report from "../Report";
import JobView from "../JobView";
import Methodology from "../Methodology";
import type { Experiment, Job, Session } from "../types";
import type { Hypothesis } from "../features/reports/types";
import WorkspaceShell from "./WorkspaceShell";
import { useHashRoute } from "./useHashRoute";
import { useArchive } from "./useArchive";
import { useCatalog } from "./useCatalog";
import { useDrafts } from "./useDrafts";
import { useRecord } from "./useRecord";
import { useJob } from "./useJob";
export default function Workspace({
  session,
  onLogout,
}: {
  session: Session;
  onLogout: () => void;
}) {
  const { route, navigate } = useHashRoute(),
    archive = useArchive(),
    catalogData = useCatalog();
  const { catalog } = catalogData,
    drafts = useDrafts(catalog, session),
    report = useRecord(route);
  const { record } = report;
  const [cancelBusy, setCancelBusy] = useState(false);
  const [runBusy, setRunBusy] = useState(false),
    [toast, setToast] = useState("");
  const [library, setLibrary] = useState<LibraryState>(INITIAL_LIBRARY);
  const [modal, setModal] = useState<"import" | "compare" | null>(null),
    [compareIds, setCompareIds] = useState<string[]>([]);
  const onError = (error: unknown) => {
    if (!ignored(error) && !(error instanceof ApiError && error.authBlocked))
      setToast(message(error));
  };
  const runs = useJob(route, (value) => {
    if (value.status === "completed" && value.record) {
      archive.recovered(value);
      void archive.reload();
      if (route !== "job/" + value.id)
        setToast("Исследование завершено. Результат доступен в архиве.");
    } else if (route !== "job/" + value.id)
      setToast(value.error ?? "Запуск завершён без результата.");
  });
  useEffect(() => {
    if (runs.job?.status === "completed" && runs.job.record)
      navigate("report/" + runs.job.record.id);
  }, [runs.job, navigate]);
  const cancel = async () => {
    if (!runs.job || cancelBusy) return;
    setCancelBusy(true);
    try {
      const value = await api.request<Job>(
        "/runs/" + runs.job.id + "/cancel",
        "POST",
      );
      runs.accept(value);
    } catch (e) {
      onError(e);
    } finally {
      setCancelBusy(false);
    }
  };
  const updated = (value: Experiment) => {
    report.updated(value);
    archive.updated(value);
  };
  const reuse = () => {
    if (record) {
      drafts.reuse(record);
      navigate("create");
    }
  };
  const testHypothesis = (hypothesis: Hypothesis, proposal: string) => {
    if (!record) return;
    drafts.reuseDraft(
      draftFromHypothesis(
        record,
        hypothesis,
        proposal,
        session.user.role === "demo",
      ),
    );
    navigate("create");
  };
  const start = async () => {
    if (runs.active) {
      navigate("job/" + runs.active.id);
      return;
    }
    if (!drafts.draft || runBusy) return;
    setRunBusy(true);
    setToast("");
    try {
      const value = await api.request<Job>(
        "/runs",
        "POST",
        runPayload(drafts.draft),
      );
      navigate("job/" + value.id);
    } catch (e) {
      onError(e);
    } finally {
      setRunBusy(false);
    }
  };
  const openSample = async () => {
    try {
      const value = await api.request<Experiment>("/sample/student_card");
      navigate("report/" + value.id);
    } catch (e) {
      onError(e);
    }
  };
  const retry = async () => {
    if (!record || !archive.pending[record.id]) return;
    try {
      const value = await api.request<Job>(
        "/runs/" + archive.pending[record.id].job + "/retry",
        "POST",
      );
      if (value.saved && value.record) {
        updated(value.record);
        setToast("");
      } else setToast(value.error ?? "Результат пока не записан.");
    } catch (e) {
      onError(e);
    }
  };
  const comparisonRecords =
    record && !archive.records.some((r) => r.id === record.id)
      ? [record, ...archive.records]
      : archive.records;
  const compare = (ids: string[]) => {
    setCompareIds(comparisonOrder(ids, comparisonRecords));
    setModal("compare");
  };
  const imported = (value: Experiment) => {
    updated(value);
    navigate("report/" + value.id);
  };
  return (
    <>
      <WorkspaceShell
        session={session}
        route={route}
        navigate={navigate}
        onLogout={onLogout}
        toast={toast}
        onDismiss={() => setToast("")}
      >
        {!route.startsWith("job/") && runs.active && (
          <a className="active-run" href={"#/job/" + runs.active.id}>
            <span className="active-run-dot" aria-hidden="true" />
            <span>
              <strong>
                {runs.active.status === "cancelling"
                  ? "Останавливаем исследование"
                  : runs.active.status === "queued"
                    ? "Исследование в очереди"
                    : "Исследование выполняется"}
              </strong>
              <span>
                {runs.active.done.toLocaleString("ru-RU")} из{" "}
                {runs.active.total.toLocaleString("ru-RU")} оценок · Открыть
                запуск
              </span>
            </span>
            <progress
              max={Math.max(1, runs.active.total)}
              value={runs.active.done}
              aria-label="Прогресс активного исследования"
            />
          </a>
        )}
        {!route.startsWith("job/") && runs.error && (
          <Notice kind="error">
            Не удалось обновить состояние запуска. {runs.error}{" "}
            <button className="text-link" onClick={runs.refresh}>
              Повторить
            </button>
          </Notice>
        )}
        {!catalog ? (
          catalogData.error ? (
            <Notice kind="error">
              {catalogData.error}
              <div>
                <Button onClick={catalogData.retry}>
                  Повторить загрузку сценариев
                </Button>
              </div>
            </Notice>
          ) : (
            <p className="help" role="status">
              Загружаем сценарии…
            </p>
          )
        ) : route === "create" ? (
          <Composer
            catalog={catalog}
            draft={drafts.draft!}
            onChange={drafts.update}
            onTemplate={drafts.choose}
            onRun={start}
            demo={session.user.role === "demo"}
            busy={runBusy}
            activeRun={Boolean(runs.active)}
          />
        ) : route.startsWith("report/") ? (
          record ? (
            <Report
              key={record.id}
              record={record}
              catalog={catalog}
              onBack={() => navigate("archive")}
              onReuse={reuse}
              onTestHypothesis={testHypothesis}
              onUpdated={updated}
              onCompare={() => compare([record.id, ""])}
              onError={onError}
              pending={archive.pending[record.id]?.error}
              onRetry={retry}
            />
          ) : report.error ? (
            <Notice kind="error">
              {report.error}
              <div className="inline-actions">
                <Button onClick={report.retry}>
                  Повторить загрузку отчёта
                </Button>
                <button
                  className="text-link"
                  onClick={() => navigate("archive")}
                >
                  Вернуться к исследованиям
                </button>
              </div>
            </Notice>
          ) : (
            <p className="help" role="status">
              Открываем сохранённый снимок…
            </p>
          )
        ) : route.startsWith("job/") ? (
          <JobView
            job={runs.job}
            error={runs.error}
            onRetry={runs.refresh}
            onCancel={cancel}
            cancelBusy={cancelBusy}
            onBackground={() => navigate("archive")}
            onBack={() => navigate("create")}
          />
        ) : route === "methodology" ? (
          <Methodology catalog={catalog} />
        ) : route === "admin" ? (
          session.user.role === "admin" ? (
            <Administration current={session.user} onError={onError} />
          ) : (
            <Notice kind="error">
              Управление доступом доступно администратору.
            </Notice>
          )
        ) : (
          <Library
            records={archive.records}
            state={library}
            onState={setLibrary}
            onNew={() => navigate("create")}
            onOpen={(id) => navigate("report/" + id)}
            onImport={() => setModal("import")}
            onSample={openSample}
            onCompare={compare}
            pending={new Set(Object.keys(archive.pending))}
            loading={archive.loading}
            error={archive.error}
            onReload={archive.reload}
          />
        )}
      </WorkspaceShell>
      {modal === "import" && (
        <ImportDialog onClose={() => setModal(null)} onImported={imported} />
      )}
      {modal === "compare" && (
        <ComparisonDialog
          ids={compareIds}
          records={comparisonRecords}
          onClose={() => setModal(null)}
          onError={onError}
        />
      )}
    </>
  );
}
