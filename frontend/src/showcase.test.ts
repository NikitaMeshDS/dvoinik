import { expect, it } from "vitest";
import { allocate, createBackend, normalizeShares } from "./showcase/backend";
import sample from "../../examples/senior-deposit.demo.json";
import type { Experiment, Scenario } from "./types";
const record = sample as unknown as Experiment;
const template: Scenario = record.scenario;
function backend() {
  return createBackend({
    session: { user: { role: "demo" } },
    catalog: { scenarios: { senior_deposit: template }, segments: {} },
    sizes: [200],
    seed: 42,
    records: { "senior_deposit|200": { ...record, id: "senior_deposit-200" } },
    insights: { "senior_deposit-200|all": { ok: true } },
    estimate: {
      system_chars: 300,
      baseline_chars: 200,
      chars_per_token: 3,
      output_tokens: 90,
      profile_chars: 260,
      latency_s: 3,
    },
    templates: { senior_deposit: template },
  });
}
it("allocates profiles with largest remainders like the server", () => {
  const shares = normalizeShares({ a: 1, b: 1, c: 1, d: 0 });
  expect(allocate(100, shares)).toEqual({ a: 34, b: 33, c: 33 });
  expect(allocate(7, normalizeShares({ x: 0.35, y: 0.35, z: 0.3 }))).toEqual({
    x: 3,
    y: 2,
    z: 2,
  });
});
it("runs unchanged templates and rejects edited scenarios", async () => {
  const api = backend();
  const started = await api("POST", "/runs", {
    scenario_key: "senior_deposit",
    scenario: template,
    n: 200,
    mock: true,
    seed: 42,
  });
  expect(started.status).toBe(200);
  const id = (started.payload as { id: string }).id;
  expect(
    ((await api("GET", "/runs/" + id, undefined)).payload as { status: string })
      .status,
  ).toBe("running");
  const done = (await api("GET", "/runs/" + id, undefined)).payload as {
    record: Experiment;
  };
  expect(done.record.report.C.yes).toBe(111);
  const insights = await api("POST", "/insights", {
    record_id: done.record.id,
    segment: "all",
  });
  expect(insights.payload).toEqual({ ok: true });
  const edited = await api("POST", "/runs", {
    scenario_key: "senior_deposit",
    scenario: { ...template, variants: { ...template.variants, A: "другое" } },
    n: 200,
    mock: true,
    seed: 42,
  });
  expect(edited.status).toBe(422);
  expect(String((edited.payload as { detail: string }).detail)).toMatch(
    /локальной версии/,
  );
  expect((await api("POST", "/compare", {})).status).toBe(422);
});
