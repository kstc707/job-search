// Minimal REST client shared by every adapter.
// - per-call timeout via AbortController
// - bounded retries with exponential backoff, ONLY for idempotent calls
//   (GETs, or POSTs that carry an idempotency key the server dedups on)
// - every failure becomes a typed error (see src/errors.js)
import { DownstreamTimeout, DownstreamUnavailable, DownstreamBadResponse, DownstreamRejected } from '../errors.js';
import { sleep } from '../lib/util.js';

export function createHttpClient({ service, baseUrl, timeoutMs = 2000, retries = 0, backoffMs = 50 }) {
  async function once(method, path, { body, headers = {}, timeoutMs: t = timeoutMs }) {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), t);
    const timeoutError = () => new DownstreamTimeout(service, `${service} did not respond within ${t} ms`);
    try {
      let res;
      try {
        res = await fetch(baseUrl + path, {
          method,
          headers: { accept: 'application/json', ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...headers },
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: ac.signal,
        });
      } catch (e) {
        if (ac.signal.aborted) throw timeoutError();
        throw new DownstreamUnavailable(service, `${service} unreachable (${e.cause?.code ?? e.message})`);
      }
      let text;
      try {
        text = await res.text();
      } catch (e) {
        if (ac.signal.aborted) throw timeoutError();
        throw new DownstreamUnavailable(service, `${service} connection dropped (${e.cause?.code ?? e.message})`);
      }
      if (res.status >= 500) {
        throw new DownstreamUnavailable(service, `${service} returned HTTP ${res.status}`, { downstreamStatus: res.status });
      }
      let data = null;
      if (text) {
        try { data = JSON.parse(text); } catch { throw new DownstreamBadResponse(service, `${service} returned a malformed response body`); }
      }
      if (res.status >= 400) {
        throw new DownstreamRejected(service, `${service} rejected the request (HTTP ${res.status})`, { downstreamStatus: res.status, body: data });
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  return async function request(method, path, opts = {}) {
    const idempotent = opts.idempotent ?? method === 'GET';
    const retryOnTimeout = opts.retryOnTimeout ?? idempotent;
    const max = idempotent ? (opts.retries ?? retries) : 0;
    for (let attempt = 0; ; attempt++) {
      try {
        return await once(method, path, opts);
      } catch (e) {
        const retryable = e instanceof DownstreamUnavailable || (e instanceof DownstreamTimeout && retryOnTimeout);
        if (!retryable || attempt >= max) {
          e.attempts = attempt + 1;
          throw e;
        }
        await sleep(backoffMs * 2 ** attempt);
      }
    }
  };
}

/** Health probe used by GET /health?deep=1: short timeout, never retried. */
export async function probe(request, path = '/health') {
  try {
    await request('GET', path, { retries: 0, timeoutMs: 500 });
    return 'up';
  } catch (e) {
    return `down (${e.code})`;
  }
}
