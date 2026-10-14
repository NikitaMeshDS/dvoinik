import { useCallback, useEffect, useRef, useState } from "react";
import { api, ignored, message } from "../api";
import type { Experiment, Job } from "../types";
import { RequestScope } from "../shared/requests";
export type PendingRecord = { record: Experiment; job: string; error: string };
export function useArchive() {
  const [records, setRecords] = useState<Experiment[]>([]);
  const [pending, setPending] = useState<Record<string, PendingRecord>>({});
  const [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const scope = useRef(new RequestScope());
  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      // Recovery remains readable when the SQLite archive cannot be read.
      await scope.current
        .run(async (signal) => {
          const recovered = await api.request<{ jobs: Job[] }>(
            "/recovery",
            "GET",
            undefined,
            signal,
          );
          if (signal.aborted) return;
          setPending(
            Object.fromEntries(
              recovered.jobs
                .filter((j) => j.record)
                .map((j) => [
                  j.record!.id,
                  {
                    record: j.record!,
                    job: j.id,
                    error: j.error ?? "Попробуйте сохранить результат ещё раз.",
                  },
                ]),
            ),
          );
          const archive = await api.request<{ records: Experiment[] }>(
            "/experiments",
            "GET",
            undefined,
            signal,
          );
          return archive.records;
        })
        .then((value) => {
          if (!value) return;
          setRecords(value);
          setPending((p) =>
            Object.fromEntries(
              Object.entries(p).filter(
                ([id]) => !value.some((r) => r.id === id),
              ),
            ),
          );
          setLoading(false);
        });
    } catch (e) {
      if (!ignored(e)) {
        setError(message(e));
        setLoading(false);
      }
    }
  }, []);
  useEffect(() => {
    void reload();
    return () => scope.current.cancel();
  }, [reload]);
  const updated = (record: Experiment) => {
    scope.current.cancel();
    setLoading(false);
    setRecords((p) => [...p.filter((r) => r.id !== record.id), record]);
    setPending((p) => {
      const next = { ...p };
      delete next[record.id];
      return next;
    });
  };
  const recovered = (job: Job) => {
    if (!job.record || job.saved) return;
    setPending((p) => ({
      ...p,
      [job.record!.id]: {
        record: job.record!,
        job: job.id,
        error: job.error ?? "Попробуйте сохранить результат ещё раз.",
      },
    }));
  };
  const allRecords = [
    ...records,
    ...Object.values(pending)
      .map((p) => p.record)
      .filter((r) => !records.some((v) => v.id === r.id)),
  ];
  return {
    records: allRecords,
    pending,
    loading,
    error,
    reload,
    updated,
    recovered,
  };
}
