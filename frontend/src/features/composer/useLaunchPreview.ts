import { useEffect, useState } from "react";
import { api, ignored, message } from "../../api";
import { draftError, runPayload } from "../../draft";
import type { Draft, Estimate } from "../../types";

type AudiencePreview = {
  counts: Record<string, number>;
  shares: Record<string, number>;
};

type Preview = AudiencePreview & { requestKey: string };

/** Loads planning data for the audience step and rejects stale responses. */
export function useLaunchPreview(draft: Draft, step: number) {
  const [preview, setPreview] = useState<Preview | null>(null),
    [previewError, setPreviewError] = useState(""),
    [loading, setLoading] = useState(false),
    [estimate, setEstimate] = useState<
      (Estimate & { requestKey: string }) | null
    >(null);
  const payload = draftError(draft) ? null : runPayload(draft);
  const estimateKey = payload
    ? JSON.stringify([payload.scenario, payload.n, payload.concurrency])
    : "";
  const previewKey = JSON.stringify([draft.weights, draft.n]);
  const activePreview = preview?.requestKey === previewKey ? preview : null;
  const activeEstimate = estimate?.requestKey === estimateKey ? estimate : null;
  useEffect(() => {
    if (step !== 1 || !payload) {
      setEstimate(null);
      return;
    }
    const controller = new AbortController();
    setEstimate(null);
    let current = true;
    const timer = window.setTimeout(() => {
      api
        .request<Estimate>(
          "/estimate",
          "POST",
          {
            scenario: payload.scenario,
            n: payload.n,
            concurrency: payload.concurrency,
          },
          controller.signal,
        )
        .then((value) => {
          if (current) setEstimate({ ...value, requestKey: estimateKey });
        })
        .catch(() => {
          if (current) setEstimate(null);
        });
    }, 300);
    return () => {
      current = false;
      window.clearTimeout(timer);
      controller.abort();
    };
    // payload пересчитывается из draft; ключ фиксирует только значимые поля.
  }, [step, estimateKey]);
  useEffect(() => {
    if (step !== 1) return;
    const controller = new AbortController();
    let alive = true;
    setLoading(true);
    setPreviewError("");
    const timer = window.setTimeout(() => {
      api
        .request<AudiencePreview>(
          "/preview",
          "POST",
          { population: draft.weights, n: draft.n },
          controller.signal,
        )
        .then((p) => {
          if (alive) setPreview({ ...p, requestKey: previewKey });
        })
        .catch((e) => {
          if (alive && !ignored(e)) {
            setPreview(null);
            setPreviewError(message(e));
          }
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, 200);
    return () => {
      alive = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [step, previewKey]);
  return { activePreview, activeEstimate, previewError, loading };
}
