import { useEffect, useState } from "react";
import { draftFromScenario, draftFromRecord } from "../draft";
import type { Catalog, Draft, Experiment, Session } from "../types";
export function useDrafts(catalog: Catalog | null, session: Session) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({}),
    [activeKey, setActiveKey] = useState("student_card");
  useEffect(() => {
    if (catalog)
      setDrafts((previous) =>
        Object.keys(previous).length
          ? previous
          : {
              student_card: draftFromScenario(
                catalog.scenarios.student_card,
                "student_card",
                session.default_mock !== false,
              ),
            },
      );
  }, [catalog, session.default_mock]);
  const choose = (key: string) => {
    if (!catalog) return;
    setDrafts((previous) =>
      previous[key]
        ? previous
        : {
            ...previous,
            [key]: draftFromScenario(
              catalog.scenarios[key],
              key,
              session.default_mock !== false,
            ),
          },
    );
    setActiveKey(key);
  };
  const reuse = (record: Experiment) => {
    setDrafts((previous) => ({
      ...previous,
      custom: draftFromRecord(record, session.user.role === "demo"),
    }));
    setActiveKey("custom");
  };
  const reuseDraft = (value: Draft) => {
    setDrafts((previous) => ({ ...previous, custom: value }));
    setActiveKey("custom");
  };
  const draft =
    drafts[activeKey] ??
    (catalog
      ? draftFromScenario(
          catalog.scenarios[activeKey],
          activeKey,
          session.default_mock !== false,
        )
      : null);
  return {
    draft,
    choose,
    reuse,
    reuseDraft,
    update: (value: Draft) =>
      setDrafts((previous) => ({ ...previous, [activeKey]: value })),
  };
}
