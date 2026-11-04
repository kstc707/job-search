// Notification adapter (email/SMS). Each message carries its outbox id as Idempotency-Key, so the
// outbox can resend safely. No inline retries: the outbox owns retry and dead-lettering.
import { probe } from './http.js';

export function createNotificationAdapter(request) {
  return {
    send({ to, channel, template, data, messageId }) {
      return request('POST', '/messages', {
        body: { to, channel, template, data },
        headers: { 'idempotency-key': messageId },
        idempotent: true,
        retryOnTimeout: false,
        retries: 0,
      });
    },
    health: () => probe(request),
  };
}
