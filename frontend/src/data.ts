import type { Experiment } from "./types";
const russianPlural = new Intl.PluralRules("ru-RU");
export function plural(
  n: number,
  one: string,
  few: string,
  many: string,
): string {
  const rule = russianPlural.select(n);
  return rule === "one" ? one : rule === "few" ? few : many;
}
export function date(value: string): string {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return "Дата из файла: " + value;
  return (
    new Intl.DateTimeFormat("ru-RU", {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: "Europe/Moscow",
    }).format(parsed) + " МСК"
  );
}
export function chronological(records: Experiment[]): Experiment[] {
  const instant = (r: Experiment) =>
    Number.isFinite(Date.parse(r.created_at))
      ? Date.parse(r.created_at)
      : Number.NEGATIVE_INFINITY;
  return [...records].sort(
    (a, b) => instant(b) - instant(a) || b.id.localeCompare(a.id),
  );
}
export function comparisonOrder(
  ids: string[],
  records: Experiment[],
): string[] {
  if (ids.length !== 2 || ids.some((id) => !id)) return [...ids];
  const dates = ids.map((id) =>
    Date.parse(records.find((r) => r.id === id)?.created_at ?? ""),
  );
  if (dates.every(Number.isFinite) && dates[0] > dates[1])
    return [ids[1], ids[0]];
  return [...ids];
}
