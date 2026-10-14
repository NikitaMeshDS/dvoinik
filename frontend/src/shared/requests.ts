import { StaleResponse } from "../api";
/** Each consumer owns a scope. Reads may finish only while their ticket is current. */
export class RequestScope {
  private current: AbortController | null = null;
  cancel() {
    this.current?.abort();
    this.current = null;
  }
  async run<T>(
    load: (signal: AbortSignal) => Promise<T>,
    commit?: (result: T) => void,
    fail?: (error: unknown) => void,
  ): Promise<T> {
    this.cancel();
    const ticket = new AbortController();
    this.current = ticket;
    try {
      const result = await load(ticket.signal);
      if (this.current !== ticket) throw new StaleResponse();
      // Commit in this turn: a chained .then leaves a gap where a newer save
      // can invalidate the ticket after our check but before the UI update.
      commit?.(result);
      return result;
    } catch (error) {
      if (this.current !== ticket) throw new StaleResponse();
      fail?.(error);
      throw error;
    }
  }
}
