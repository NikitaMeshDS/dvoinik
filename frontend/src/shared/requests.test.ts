import { expect, it } from "vitest";
import { RequestScope } from "./requests";
import { StaleResponse } from "../api";
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
it("returns the newest read and discards an older response even if its transport ignores abort", async () => {
  const scope = new RequestScope();
  const old = deferred<string>(),
    current = deferred<string>();
  const first = scope.run(() => old.promise);
  const second = scope.run(() => current.promise);
  current.resolve("new survey");
  await expect(second).resolves.toBe("new survey");
  old.resolve("old survey");
  await expect(first).rejects.toBeInstanceOf(StaleResponse);
});
it("a successful save can invalidate an earlier read instead of letting it erase the saved result", async () => {
  const scope = new RequestScope(),
    read = deferred<string>();
  const pending = scope.run(() => read.promise);
  scope.cancel();
  read.resolve("before save");
  await expect(pending).rejects.toBeInstanceOf(StaleResponse);
  await expect(scope.run(async () => "after save")).resolves.toBe("after save");
});
it("disposal aborts the transport and withholds its late error from a new screen", async () => {
  const scope = new RequestScope(),
    read = deferred<string>();
  let transportSignal!: AbortSignal;
  const pending = scope.run((signal) => {
    transportSignal = signal;
    return read.promise;
  });
  scope.cancel();
  expect(transportSignal.aborted).toBe(true);
  read.reject(new Error("old screen unavailable"));
  await expect(pending).rejects.toBeInstanceOf(StaleResponse);
});
