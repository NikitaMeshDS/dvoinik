import type { Catalog, Draft } from "../types";

const PREFIX = "dvoinik:drafts:v1:";
const DORMANT_PREFIX = PREFIX + "dormant:";
const BACKUP_PREFIX = PREFIX + "backup:";
export type DraftBackups = Record<string, { draft: Draft; step: number }>;
export type DraftSnapshot = {
  version: 1;
  owner: string;
  activeKey: string;
  drafts: Record<string, Draft>;
  steps: Record<string, number>;
};
const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
function validDraft(value: unknown, key: string): value is Draft {
  if (!object(value) || value.key !== key) return false;
  if (
    value.restoredAsCustom !== undefined &&
    (key !== "custom" || value.restoredAsCustom !== true)
  )
    return false;
  if (
    !["title", "description", "question"].every(
      (field) => typeof value[field] === "string",
    )
  )
    return false;
  if (
    !object(value.variants) ||
    !Object.entries(value.variants).every(
      ([variant, text]) => /^[A-E]$/.test(variant) && typeof text === "string",
    )
  )
    return false;
  if (
    !Number.isInteger(value.variantCount) ||
    Number(value.variantCount) < 2 ||
    Number(value.variantCount) > 5
  )
    return false;
  if (!object(value.weights) || !Object.values(value.weights).every(finite))
    return false;
  if (
    !Array.isArray(value.objections) ||
    !value.objections.every((text) => typeof text === "string")
  )
    return false;
  if (
    ![value.n, value.seed, value.concurrency].every(finite) ||
    typeof value.mock !== "boolean"
  )
    return false;
  if (value.depositMinimumRub !== undefined && !finite(value.depositMinimumRub))
    return false;
  if (value.origin !== undefined) {
    const origin = value.origin;
    if (
      !object(origin) ||
      !["iteration", "hypothesis"].includes(String(origin.kind)) ||
      typeof origin.record_id !== "string" ||
      typeof origin.title !== "string"
    )
      return false;
    if (
      origin.hypothesis_id !== undefined &&
      (typeof origin.hypothesis_id !== "string" ||
        !/^[a-f0-9]{64}$/.test(origin.hypothesis_id))
    )
      return false;
    if (
      !["lever", "change", "variant"].every(
        (field) =>
          origin[field] === undefined || typeof origin[field] === "string",
      )
    )
      return false;
  }
  return true;
}
function readSnapshot(
  key: string,
  owner: string,
): {
  snapshot: DraftSnapshot | null;
  warning: string;
} {
  try {
    const text = sessionStorage.getItem(key);
    if (!text) return { snapshot: null, warning: "" };
    if (text.length > 2_000_000) throw new Error("Draft too large");
    const value: unknown = JSON.parse(text);
    if (
      !object(value) ||
      value.version !== 1 ||
      value.owner !== owner ||
      typeof value.activeKey !== "string" ||
      !object(value.drafts) ||
      !object(value.steps)
    )
      throw new Error("Invalid draft snapshot");
    if (
      !Object.hasOwn(value.drafts, value.activeKey) ||
      !Object.keys(value.drafts).length
    )
      throw new Error("Missing active draft");
    if (
      !Object.entries(value.drafts).every(([key, draft]) =>
        validDraft(draft, key),
      )
    )
      throw new Error("Invalid draft");
    if (
      !Object.entries(value.steps).every(
        ([key, step]) =>
          Object.hasOwn(value.drafts as object, key) &&
          (step === 0 || step === 1),
      )
    )
      throw new Error("Invalid stage");
    return { snapshot: value as DraftSnapshot, warning: "" };
  } catch {
    return {
      snapshot: null,
      warning: "Не удалось восстановить черновик. Открыт исходный шаблон.",
    };
  }
}

export function readDrafts(owner: string) {
  const encoded = encodeURIComponent(owner);
  const current = readSnapshot(PREFIX + encoded, owner);
  const dormant = readSnapshot(DORMANT_PREFIX + encoded, owner);
  const savedBackups = readSnapshot(BACKUP_PREFIX + encoded, owner);
  const snapshot = current.snapshot ?? dormant.snapshot;
  const backups: DraftBackups = Object.fromEntries(
    Object.entries({
      ...dormant.snapshot?.drafts,
      ...savedBackups.snapshot?.drafts,
    })
      .filter(([key, draft]) => {
        const active = current.snapshot?.drafts[key];
        return (
          Object.hasOwn(savedBackups.snapshot?.drafts ?? {}, key) ||
          (active && JSON.stringify(active) !== JSON.stringify(draft))
        );
      })
      .map(([key, draft]) => [
        key,
        {
          draft,
          step:
            savedBackups.snapshot?.steps[key] ??
            dormant.snapshot?.steps[key] ??
            0,
        },
      ]),
  );
  return {
    backups,
    snapshot: snapshot && {
      ...snapshot,
      drafts: { ...dormant.snapshot?.drafts, ...current.snapshot?.drafts },
      steps: {
        ...Object.fromEntries(
          Object.entries(dormant.snapshot?.steps ?? {}).filter(
            ([key]) => !Object.hasOwn(current.snapshot?.drafts ?? {}, key),
          ),
        ),
        ...current.snapshot?.steps,
      },
    },
    warning:
      current.warning ||
      ((dormant.warning || savedBackups.warning) &&
        "Не удалось загрузить часть сохранённых копий черновиков."),
  };
}

function selectDrafts(
  snapshot: DraftSnapshot,
  keys: string[],
  activeKey: string,
): DraftSnapshot {
  return {
    ...snapshot,
    activeKey,
    drafts: Object.fromEntries(keys.map((key) => [key, snapshot.drafts[key]])),
    steps: Object.fromEntries(
      keys
        .filter((key) => Object.hasOwn(snapshot.steps, key))
        .map((key) => [key, snapshot.steps[key]]),
    ),
  };
}

function storeBackups(key: string, owner: string, backups: DraftBackups) {
  const entries = Object.entries(backups);
  if (!entries.length) {
    sessionStorage.removeItem(key);
    return;
  }
  sessionStorage.setItem(
    key,
    JSON.stringify({
      version: 1,
      owner,
      activeKey: entries[0][0],
      drafts: Object.fromEntries(
        entries.map(([key, value]) => [key, value.draft]),
      ),
      steps: Object.fromEntries(
        entries.map(([key, value]) => [key, value.step]),
      ),
    }),
  );
}

export function saveDrafts(
  snapshot: DraftSnapshot,
  catalog: Catalog,
  backups: DraftBackups,
): boolean {
  try {
    const encoded = encodeURIComponent(snapshot.owner);
    const dormantKey = DORMANT_PREFIX + encoded;
    const backupKey = BACKUP_PREFIX + encoded;
    const known = (key: string) => Object.hasOwn(catalog.scenarios, key);
    const keys = Object.keys(snapshot.drafts);
    const available = selectDrafts(
      snapshot,
      keys.filter(known),
      snapshot.activeKey,
    );
    const hidden = keys.filter((key) => !known(key));
    if (Object.keys(backups).length) {
      // Preserve unresolved copies until the selected draft is written.
      const previous = readSnapshot(backupKey, snapshot.owner).snapshot;
      const oldBackups = Object.fromEntries(
        Object.entries(previous?.drafts ?? {}).map(([key, draft]) => [
          key,
          { draft, step: previous?.steps[key] ?? 0 },
        ]),
      );
      storeBackups(backupKey, snapshot.owner, { ...oldBackups, ...backups });
    }
    if (hidden.length) {
      // Stage both previously hidden and newly missing drafts before updating v1.
      // This preserves a copy if the browser rejects the main write.
      const previous = readSnapshot(dormantKey, snapshot.owner).snapshot;
      const protectedKeys = [
        ...new Set([...hidden, ...Object.keys(previous?.drafts ?? {})]),
      ].filter((key) => Object.hasOwn(snapshot.drafts, key));
      sessionStorage.setItem(
        dormantKey,
        JSON.stringify(selectDrafts(snapshot, protectedKeys, hidden[0])),
      );
    }
    sessionStorage.setItem(PREFIX + encoded, JSON.stringify(available));
    if (hidden.length) {
      sessionStorage.setItem(
        dormantKey,
        JSON.stringify(selectDrafts(snapshot, hidden, hidden[0])),
      );
    } else {
      sessionStorage.removeItem(dormantKey);
    }
    storeBackups(backupKey, snapshot.owner, backups);
    return true;
  } catch {
    return false;
  }
}
/** Remove only our draft namespace, including other owners left in this tab. */
export function clearDrafts(): void {
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index--) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(PREFIX)) sessionStorage.removeItem(key);
    }
  } catch {
    // Storage may be blocked; the workspace is still unmounted on session loss.
  }
}
