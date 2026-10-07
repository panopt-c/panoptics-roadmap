/**
 * Api — the client's only door to the local game server (docs/ARCHITECTURE.md §3.3, §3.4, §4.4).
 *
 * Requests
 *  - Every call carries the per-launch token as `X-NS-Token`. The custom header forces a CORS
 *    preflight the server never approves, which is what keeps other websites out.
 *  - One AbortController per request enforces the timeout across the whole exchange
 *    (headers *and* body): 15 s, or 60 s for `hack`, which runs the player's code.
 *  - Failures always reject with `ApiError {status, message}`: the server's `{"error"}` text
 *    for 4xx/5xx, status 408 for a timeout and status 0 when the server is unreachable, so
 *    callers can show one readable line without inspecting fetch internals.
 *
 * Events
 *  `events(onEvent, {onStatus})` opens `/api/events?token=` (EventSource cannot send headers)
 *  and dispatches the named server events (`hello`, `file`, `cutscene`, `state`) as
 *  `onEvent(name, data)`. The browser's built-in reconnect is not used: a 401/403 makes an
 *  EventSource give up for good, so on any error we close it and reconnect ourselves with
 *  jittered exponential backoff (0.6 s → 15 s), immediately when the OS reports the network
 *  is back. `onStatus('open', {reconnected})` / `onStatus('down', {attempt, delay})` let the
 *  shell show and clear its "link lost" banner. The returned `close()` stops everything.
 */
const TIMEOUT_MS = 15_000;
const HACK_TIMEOUT_MS = 60_000;
const BACKOFF_BASE_MS = 600;
const BACKOFF_MAX_MS = 15_000;

/** Named SSE events the server sends (§3.4). */
export const SERVER_EVENTS = Object.freeze(['hello', 'file', 'cutscene', 'state']);

export class ApiError extends Error {
  /**
   * @param {number} status  HTTP status; 0 = server unreachable, 408 = timed out
   * @param {string} message human-readable reason (the server's `error` field when it sent one)
   */
  constructor(status, message) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }

  /** True when the request never reached the server (network down, server stopped). */
  get offline() {
    return this.status === 0;
  }
}

const segment = (id) => encodeURIComponent(String(id));

export class Api {
  #token;
  #base;

  /**
   * @param {string} token  the `ns-token` meta value
   * @param {{base?: string}} [options]  URL prefix (tests); same origin by default
   */
  constructor(token, { base = '' } = {}) {
    this.#token = String(token ?? '');
    this.#base = base;
  }

  state() {
    return this.#request('GET', '/api/state');
  }

  mission(id) {
    return this.#request('GET', `/api/missions/${segment(id)}`);
  }

  deploy(id) {
    return this.#request('POST', `/api/missions/${segment(id)}/deploy`);
  }

  saveSource(id, source) {
    return this.#request('PUT', `/api/missions/${segment(id)}/source`, { body: { source: String(source) } });
  }

  hack(id) {
    return this.#request('POST', `/api/missions/${segment(id)}/hack`, { timeout: HACK_TIMEOUT_MS });
  }

  reset(id) {
    return this.#request('POST', `/api/missions/${segment(id)}/reset`);
  }

  cutscene(id) {
    return this.#request('POST', `/api/missions/${segment(id)}/cutscene`);
  }

  /**
   * Subscribe to server events. Returns `close()`.
   * @param {(name: string, data: any) => void} onEvent
   * @param {{names?: string[], onStatus?: (status: 'open'|'down', info: object) => void}} [options]
   */
  events(onEvent, { names = SERVER_EVENTS, onStatus } = {}) {
    if (typeof EventSource !== 'function') return () => {};
    const url = `${this.#base}/api/events?token=${encodeURIComponent(this.#token)}`;
    let source = null;
    let timer = 0;
    let attempt = 0;
    let opens = 0;
    let closed = false;

    // Built once: the same listener functions are attached to every EventSource we create.
    const listeners = names.map((name) => [
      name,
      (event) => {
        let data = null;
        try {
          data = event.data ? JSON.parse(event.data) : null;
        } catch {
          console.warn(`[api] ignored malformed "${name}" event`);
          return;
        }
        onEvent(name, data);
      },
    ]);

    const connect = () => {
      timer = 0;
      if (closed) return;
      const es = new EventSource(url);
      source = es;
      for (const [name, fn] of listeners) es.addEventListener(name, fn);
      es.onopen = () => {
        if (source !== es) return;
        attempt = 0;
        opens += 1;
        onStatus?.('open', { reconnected: opens > 1 });
      };
      es.onerror = () => {
        if (source !== es) return;
        es.close();
        source = null;
        if (closed) return;
        const exp = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** attempt);
        const delay = Math.round(exp * (0.75 + Math.random() * 0.5));
        attempt += 1;
        timer = setTimeout(connect, delay);
        onStatus?.('down', { attempt, delay });
      };
    };

    const retryNow = () => {
      if (!timer || closed) return;
      clearTimeout(timer);
      connect();
    };
    addEventListener('online', retryNow);
    connect();

    return () => {
      closed = true;
      clearTimeout(timer);
      timer = 0;
      source?.close();
      source = null;
      removeEventListener('online', retryNow);
    };
  }

  async #request(method, path, { body, timeout = TIMEOUT_MS } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const headers = { 'X-NS-Token': this.#token, Accept: 'application/json' };
    let payload;
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      payload = JSON.stringify(body);
    }
    try {
      let response;
      try {
        response = await fetch(this.#base + path, {
          method,
          headers,
          body: payload,
          signal: controller.signal,
          cache: 'no-store',
          credentials: 'same-origin',
        });
      } catch {
        throw controller.signal.aborted
          ? new ApiError(408, `the server took longer than ${Math.round(timeout / 1000)} s to answer`)
          : new ApiError(0, 'the game server is unreachable');
      }

      let text = '';
      try {
        text = await response.text();
      } catch {
        throw controller.signal.aborted
          ? new ApiError(408, `the server took longer than ${Math.round(timeout / 1000)} s to answer`)
          : new ApiError(0, 'the connection dropped mid-response');
      }

      let data = null;
      if (text) {
        try {
          data = JSON.parse(text);
        } catch {
          if (response.ok) throw new ApiError(502, `malformed response from ${path}`);
        }
      }
      if (!response.ok) {
        const reason = data && typeof data.error === 'string' ? data.error : response.statusText || 'request failed';
        throw new ApiError(response.status, reason);
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }
}
