import { StaleResponse } from "../api";
/** Each consumer owns a scope. Reads may finish only while their ticket is current. */
export class RequestScope {
  private current: AbortController | null = null;
  cancel() {
    this.current?.abort();
    this.current = null;
  }
  async run<T>(load: (signal: AbortSignal) => Promise<T>): Promise<T> {
    this.cancel();
    const ticket = new AbortController();
    this.current = ticket;
    try {
      const result = await load(ticket.signal);
      if (this.current !== ticket) throw new StaleResponse();
      return result;
    } catch (error) {
      if (this.current !== ticket) throw new StaleResponse();
      throw error;
    }
  }
}
