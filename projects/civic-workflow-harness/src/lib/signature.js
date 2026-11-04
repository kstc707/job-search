// HMAC-SHA256 webhook signatures: header `x-signature: sha256=<hex of HMAC(secret, raw body)>`.
import { createHmac, timingSafeEqual } from 'node:crypto';

export function sign(secret, rawBody) {
  return 'sha256=' + createHmac('sha256', secret).update(rawBody).digest('hex');
}

export function verify(secret, rawBody, header) {
  if (typeof header !== 'string' || !header.startsWith('sha256=')) return false;
  const expected = Buffer.from(sign(secret, rawBody));
  const got = Buffer.from(header);
  return expected.length === got.length && timingSafeEqual(expected, got);
}
