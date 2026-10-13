import { expect, it } from "vitest";
import { comparisonOrder, chronological, date } from "./data";
import type { Experiment } from "./types";
const older = {
  id: "older",
  created_at: "2026-10-14T00:30:00+03:00",
} as Experiment;
const newer = {
  id: "newer",
  created_at: "2026-10-13T22:00:00+00:00",
} as Experiment;
it("orders archived studies by instant rather than date string or timezone", () => {
  const source = [older, newer];
  expect(chronological(source).map((r) => r.id)).toEqual(["newer", "older"]);
  expect(source).toEqual([older, newer]);
});
it("uses older-first comparison regardless of newest-first selection and preserves a single choice", () => {
  expect(comparisonOrder(["newer", "older"], [older, newer])).toEqual([
    "older",
    "newer",
  ]);
  expect(comparisonOrder(["newer", ""], [older, newer])).toEqual(["newer", ""]);
});
it("accepted imported basic ISO dates do not crash the workspace if JavaScript cannot parse them", () => {
  expect(() => date("20261014T003000+0300")).not.toThrow();
  expect(date("20261014T003000+0300")).toContain("20261014");
});
