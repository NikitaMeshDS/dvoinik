import { useEffect, useState } from "react";
import { draftFromScenario, draftFromRecord } from "../draft";
import type { Catalog, Draft, Experiment, Session } from "../types";
import {
  readDrafts,
  saveDrafts,
  type DraftSnapshot,
  type DraftBackups,
} from "./draftStorage";

type DraftState = DraftSnapshot & {
  ready: boolean;
  warning: string;
  backups: DraftBackups;
};
function initial(catalog: Catalog | null, session: Session): DraftState {
  const owner = session.user.id;
  const restored = catalog
    ? readDrafts(owner)
    : { snapshot: null, warning: "", backups: {} };
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
  let snapshot = restored.snapshot ?? fallback;
  let warning = restored.warning;
  if (catalog && !Object.hasOwn(catalog.scenarios, snapshot.activeKey)) {
    // Keep dormant drafts so that they can reopen if the template returns.
    const availableKey = Object.keys(snapshot.drafts).find((key) =>
      Object.hasOwn(catalog.scenarios, key),
    );
    const nextKey = availableKey ?? fallback.activeKey;
    snapshot = {
      ...snapshot,
      activeKey: nextKey,
      drafts: availableKey
        ? snapshot.drafts
        : { ...fallback.drafts, ...snapshot.drafts },
      steps: { ...snapshot.steps, [nextKey]: 0 },
    };
    warning =
      "Прежний шаблон больше недоступен. Проверьте открытый сценарий перед запуском.";
  }
  return {
    ...snapshot,
    ready: catalog !== null,
    backups: restored.backups,
    warning,
  };
}
export function useDrafts(catalog: Catalog | null, session: Session) {
  const owner = session.user.id;
  const [state, setState] = useState(() => initial(catalog, session));
  const [saved, setSaved] = useState(false);
  const available =
    catalog !== null &&
    state.ready &&
    state.owner === owner &&
    Object.hasOwn(catalog.scenarios, state.activeKey);
  useEffect(() => {
    if (catalog && !available) {
      setState(initial(catalog, session));
      setSaved(false);
    }
  }, [catalog, owner, available, session.default_mock]);
  useEffect(() => {
    if (!catalog || !available) return;
    const { version, activeKey, drafts, steps, backups } = state;
    setSaved(
      saveDrafts(
        { version, owner, activeKey, drafts, steps },
        catalog,
        backups,
      ),
    );
  }, [state, owner, catalog, available]);
  const visible = available ? state : initial(catalog, session);
  const change = (
    patch: Partial<DraftSnapshot & { backups: DraftBackups }>,
  ) => {
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
    const key = value.key;
    if (!available || !catalog || !Object.hasOwn(catalog.scenarios, key))
      return false;
    const existing = state.drafts[key];
    const base = draftFromScenario(
      catalog.scenarios[key],
      key,
      session.default_mock !== false,
    );
    if (
      existing &&
      JSON.stringify(existing) !== JSON.stringify(base) &&
      !window.confirm(
        "Заменить незавершённый черновик? Отмена сохранит текущие правки.",
      )
    )
      return false;
    change({
      drafts: { ...state.drafts, [key]: value },
      activeKey: key,
      steps: { ...state.steps, [key]: 0 },
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
  const copies = visible.backups[visible.activeKey] ?? [];
  const resolveBackup = (restore: boolean, index = 0) => {
    const backup = copies[index];
    if (
      !catalog ||
      !available ||
      !backup ||
      !window.confirm(
        restore
          ? "Заменить открытый черновик сохранённой копией?"
          : "Оставить открытый черновик и удалить сохранённую копию?",
      )
    )
      return;
    const key = state.activeKey;
    const backups = { ...state.backups };
    if (copies.length > 1) backups[key] = copies.filter((_, i) => i !== index);
    else delete backups[key];
    const drafts = restore ? { ...state.drafts, [key]: backup } : state.drafts;
    const steps = restore ? { ...state.steps, [key]: 0 } : state.steps;
    const written = saveDrafts(
      { version: state.version, owner, activeKey: key, drafts, steps },
      catalog,
      backups,
    );
    setSaved(written);
    if (written) change({ backups, drafts, steps });
  };
  return {
    draft: visible.drafts[visible.activeKey] ?? null,
    backups: copies,
    resolveBackup,
    step: visible.steps[visible.activeKey] ?? 0,
    setStep: (step: number) => {
      if (step === 0 || step === 1)
        change({ steps: { ...state.steps, [state.activeKey]: step } });
    },
    status: [
      visible.warning,
      saved && available
        ? !visible.warning &&
          "Сохранено в этой вкладке. После обновления черновик восстановится; при выходе он удалится."
        : "Черновик не сохранён в браузере. Не обновляйте страницу; редактирование доступно.",
    ]
      .filter(Boolean)
      .join(" "),
    choose,
    reuseDraft,
    reset,
    reuse: (record: Experiment) =>
      reuseDraft(draftFromRecord(record, session.user.role === "demo")),
    update: (value: Draft) =>
      change({ drafts: { ...state.drafts, [state.activeKey]: value } }),
  };
}
