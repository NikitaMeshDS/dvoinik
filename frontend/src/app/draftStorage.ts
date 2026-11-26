import type { Catalog, Draft } from "../types";

const SNAPSHOT_LIMIT = 2_000_000;
const PREFIX = "dvoinik:drafts:v1:";
const DORMANT_PREFIX = PREFIX + "dormant:";
const LEGACY_BACKUP_PREFIX = PREFIX + "backup:";
const BACKUP_PREFIX = PREFIX + "alternates:";
export type DraftBackups = Record<string, Draft[]>;
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
    if (text.length > SNAPSHOT_LIMIT) throw new Error("Draft too large");
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

function readBackups(
  key: string,
  owner: string,
): { backups: DraftBackups; warning: string } {
  try {
    const text = sessionStorage.getItem(key);
    if (!text) return { backups: {}, warning: "" };
    if (text.length > SNAPSHOT_LIMIT) throw new Error("Draft too large");
    const value: unknown = JSON.parse(text);
    if (
      object(value) &&
      value.version === 2 &&
      value.owner === owner &&
      object(value.backups) &&
      Object.entries(value.backups).every(
        ([key, copies]) =>
          Array.isArray(copies) &&
          copies.every((draft) => validDraft(draft, key)),
      )
    ) {
      return { backups: value.backups as DraftBackups, warning: "" };
    }
    // The first release stored a single copy in the v1 snapshot format.
    const legacy = readSnapshot(key, owner);
    return {
      backups: Object.fromEntries(
        Object.entries(legacy.snapshot?.drafts ?? {}).map(([key, draft]) => [
          key,
          [draft],
        ]),
      ),
      warning: legacy.warning,
    };
  } catch {
    return { backups: {}, warning: "Не удалось прочитать сохранённые копии." };
  }
}

function mergeBackups(base: DraftBackups, extra: DraftBackups): DraftBackups {
  const keys = new Set([...Object.keys(base), ...Object.keys(extra)]);
  return Object.fromEntries(
    [...keys].map((key) => {
      const copies = [...(base[key] ?? []), ...(extra[key] ?? [])];
      const unique = new Map(
        copies.map((draft) => [JSON.stringify(draft), draft]),
      );
      return [key, [...unique.values()]];
    }),
  );
}

export function readDrafts(owner: string) {
  const encoded = encodeURIComponent(owner);
  const current = readSnapshot(PREFIX + encoded, owner);
  const dormant = readSnapshot(DORMANT_PREFIX + encoded, owner);
  const savedBackups = readBackups(BACKUP_PREFIX + encoded, owner);
  const legacyBackups = readBackups(LEGACY_BACKUP_PREFIX + encoded, owner);
  const snapshot = current.snapshot ?? dormant.snapshot;
  const collisions: DraftBackups = Object.fromEntries(
    Object.entries(dormant.snapshot?.drafts ?? {})
      .filter(([key, draft]) => {
        const active = current.snapshot?.drafts[key];
        return active && JSON.stringify(active) !== JSON.stringify(draft);
      })
      .map(([key, draft]) => [key, [draft]]),
  );
  const backups = mergeBackups(
    mergeBackups(savedBackups.backups, legacyBackups.backups),
    collisions,
  );
  for (const [key, copies] of Object.entries(backups)) {
    const active =
      current.snapshot?.drafts[key] ?? dormant.snapshot?.drafts[key];
    const distinct = copies.filter(
      (draft) => JSON.stringify(draft) !== JSON.stringify(active),
    );
    if (distinct.length) backups[key] = distinct;
    else delete backups[key];
  }
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
      ((dormant.warning || savedBackups.warning || legacyBackups.warning) &&
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

function encodeSnapshot(value: unknown): string {
  const text = JSON.stringify(value);
  if (text.length > SNAPSHOT_LIMIT) throw new Error("Draft too large");
  return text;
}

function storeBackups(key: string, owner: string, backups: DraftBackups) {
  if (!Object.keys(backups).length) {
    sessionStorage.removeItem(key);
    return;
  }
  const text = encodeSnapshot({ version: 2, owner, backups });
  if (sessionStorage.getItem(key) !== text) sessionStorage.setItem(key, text);
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
    const main = encodeSnapshot(available);
    const hidden = keys.filter((key) => !known(key));
    if (Object.keys(backups).length) {
      // Preserve unresolved copies until the selected draft is written.
      const previous = readBackups(backupKey, snapshot.owner);
      storeBackups(
        backupKey,
        snapshot.owner,
        mergeBackups(previous.backups, backups),
      );
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
        encodeSnapshot(selectDrafts(snapshot, protectedKeys, hidden[0])),
      );
    }
    sessionStorage.setItem(PREFIX + encoded, main);
    if (hidden.length) {
      sessionStorage.setItem(
        dormantKey,
        encodeSnapshot(selectDrafts(snapshot, hidden, hidden[0])),
      );
    } else {
      sessionStorage.removeItem(dormantKey);
    }
    storeBackups(backupKey, snapshot.owner, backups);
    sessionStorage.removeItem(LEGACY_BACKUP_PREFIX + encoded);
    return true;
  } catch {
    return false;
  }
}

function sameDraft(left: DraftSnapshot, right: DraftSnapshot, key: string) {
  return (
    JSON.stringify(left.drafts[key]) === JSON.stringify(right.drafts[key]) &&
    (left.steps[key] ?? 0) === (right.steps[key] ?? 0)
  );
}

export function saveActiveDrafts(
  snapshot: DraftSnapshot,
  catalog: Catalog,
): boolean {
  try {
    const encoded = encodeURIComponent(snapshot.owner);
    const mainKey = PREFIX + encoded;
    const dormantKey = DORMANT_PREFIX + encoded;
    const keys = Object.keys(snapshot.drafts);
    const known = (key: string) => Object.hasOwn(catalog.scenarios, key);
    const main = encodeSnapshot(
      selectDrafts(snapshot, keys.filter(known), snapshot.activeKey),
    );
    const hidden = keys.filter((key) => !known(key));
    const dormant = readSnapshot(dormantKey, snapshot.owner).snapshot;
    if (hidden.length) {
      // Replacing the main slot must leave a durable copy of every hidden draft and its step.
      if (!dormant || hidden.some((key) => !sameDraft(dormant, snapshot, key)))
        return false;
    }
    const previous = dormant && readSnapshot(mainKey, snapshot.owner).snapshot;
    if (dormant && previous) {
      const dormantKeys = Object.keys(dormant.drafts);
      const remaining = dormantKeys.filter(
        (key) =>
          !known(key) ||
          !Object.hasOwn(snapshot.drafts, key) ||
          !sameDraft(dormant, previous, key) ||
          sameDraft(previous, snapshot, key),
      );
      if (remaining.length < dormantKeys.length) {
        // Remove identical staging copies while the previous main snapshot is still durable.
        try {
          if (remaining.length) {
            const activeKey = remaining.includes(dormant.activeKey)
              ? dormant.activeKey
              : remaining[0];
            sessionStorage.setItem(
              dormantKey,
              encodeSnapshot(selectDrafts(dormant, remaining, activeKey)),
            );
          } else {
            sessionStorage.removeItem(dormantKey);
          }
        } catch {
          // Prefer saving current edits even when the browser refuses to prune an old copy.
        }
      }
    }
    sessionStorage.setItem(mainKey, main);
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
