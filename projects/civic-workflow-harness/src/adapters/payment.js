// Payment adapter. Charge creation carries an Idempotency-Key, so the provider dedups it and a retry
// after a 5xx cannot double-charge. A *timeout* is not retried inline: the outcome is unknown, so the
// workflow records a reconciliation item instead of making the applicant wait (see service.js).
import { DownstreamRejected, DownstreamBadResponse } from '../errors.js';
import { probe } from './http.js';

function checkCharge(c) {
  if (!c || typeof c.id !== 'string' || typeof c.status !== 'string') {
    throw new DownstreamBadResponse('payment', 'payment returned a charge without id/status');
  }
  return c;
}

export function createPaymentAdapter(request) {
  return {
    async createCharge({ permitId, amountCents, currency, idempotencyKey, callbackUrl }) {
      const c = await request('POST', '/charges', {
        body: { permitId, amountCents, currency, callbackUrl },
        headers: { 'idempotency-key': idempotencyKey },
        idempotent: true,
        retryOnTimeout: false,
      });
      return checkCharge(c);
    },
    /** Look a charge up by idempotency key; null when the provider never created it. */
    async findCharge(idempotencyKey) {
      try {
        return checkCharge(await request('GET', `/charges?idempotencyKey=${encodeURIComponent(idempotencyKey)}`));
      } catch (e) {
        if (e instanceof DownstreamRejected && e.downstreamStatus === 404) return null;
        throw e;
      }
    },
    health: () => probe(request),
  };
}
