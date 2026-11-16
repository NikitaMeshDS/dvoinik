import { useEffect, useState } from "react";
import { draftFromScenario, draftFromRecord } from "../draft";
import type { Catalog, Draft, Experiment, Session } from "../types";
import { readDrafts, saveDrafts, type DraftSnapshot } from "./draftStorage";

type DraftState = DraftSnapshot & { ready: boolean; warning: string };
function initial(catalog: Catalog | null, session: Session): DraftState {
  const owner = session.user.id;
  const restored = catalog
    ? readDrafts(owner, catalog)
    : { snapshot: null, warning: "" };
  const activeKey =
    catalog && !catalog.scenarios.student_card
      ? Object.keys(catalog.scenarios)[0]
      : "student_card";
  const fallback: DraftSnapshot = {
    version: 1,
    owner,
    activeKey,
    steps: {},
    drafts: catalog
      ? {
          [activeKey]: draftFromScenario(
            catalog.scenarios[activeKey],
            activeKey,
            session.default_mock !== false,
          ),
        }
      : {},
  };
  return {
    ...(restored.snapshot ?? fallback),
    ready: catalog !== null,
    warning: restored.warning,
  };
}
export function useDrafts(catalog: Catalog | null, session: Session) {
  const owner = session.user.id;
  const [state, setState] = useState(() => initial(catalog, session));
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (catalog && (!state.ready || state.owner !== owner)) {
      setState(initial(catalog, session));
      setSaved(false);
    }
  }, [catalog, owner, state.ready, state.owner, session.default_mock]);
  useEffect(() => {
    if (!state.ready || state.owner !== owner) return;
    const { version, activeKey, drafts, steps } = state;
    setSaved(saveDrafts({ version, owner, activeKey, drafts, steps }));
  }, [state, owner]);
  const available = state.ready && state.owner === owner;
  const visible = available ? state : initial(catalog, session);
  const change = (patch: Partial<DraftSnapshot>) => {
    if (!available) return;
    setState((previous) =>
      previous.owner === owner
        ? { ...previous, ...patch, warning: "" }
        : previous,
    );
  };
  const choose = (key: string) => {
    if (!catalog || !available || !Object.hasOwn(catalog.scenarios, key))
      return;
    change({
      activeKey: key,
      drafts: state.drafts[key]
        ? state.drafts
        : {
            ...state.drafts,
            [key]: draftFromScenario(
              catalog.scenarios[key],
              key,
              session.default_mock !== false,
            ),
          },
    });
  };
  const reuseDraft = (value: Draft): boolean => {
    if (!available) return false;
    const existing = state.drafts.custom;
    const base =
      catalog?.scenarios.custom &&
      draftFromScenario(
        catalog.scenarios.custom,
        "custom",
        session.default_mock !== false,
      );
    if (
      existing &&
      JSON.stringify(existing) !== JSON.stringify(base) &&
      !window.confirm(
        "Заменить незавершённый черновик своего сценария новой итерацией? Отмена сохранит прежний черновик.",
      )
    )
      return false;
    change({
      drafts: { ...state.drafts, custom: { ...value, key: "custom" } },
      activeKey: "custom",
      steps: { ...state.steps, custom: 0 },
    });
    return true;
  };
  const reset = () => {
    if (
      !catalog ||
      !available ||
      !window.confirm(
        "Начать заново? Изменения текущего черновика будут заменены исходным шаблоном.",
      )
    )
      return;
    change({
      drafts: {
        ...state.drafts,
        [state.activeKey]: draftFromScenario(
          catalog.scenarios[state.activeKey],
          state.activeKey,
          session.default_mock !== false,
        ),
      },
      steps: { ...state.steps, [state.activeKey]: 0 },
    });
  };
  return {
    draft: visible.drafts[visible.activeKey] ?? null,
    step: visible.steps[visible.activeKey] ?? 0,
    setStep: (step: number) => {
      if (step === 0 || step === 1)
        change({ steps: { ...state.steps, [state.activeKey]: step } });
    },
    status:
      visible.warning ||
      (saved && available
        ? "Сохранено в этой вкладке. После обновления черновик восстановится; при выходе он удалится."
        : "Черновик не сохранён в браузере. Не обновляйте страницу; редактирование доступно."),
    choose,
    reuseDraft,
    reset,
    reuse: (record: Experiment) =>
      reuseDraft(draftFromRecord(record, session.user.role === "demo")),
    update: (value: Draft) =>
      change({ drafts: { ...state.drafts, [state.activeKey]: value } }),
  };
}
