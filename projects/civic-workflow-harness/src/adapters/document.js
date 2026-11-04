// Document adapter. Upload is a non-idempotent POST, so it is never retried automatically.
import { DownstreamBadResponse } from '../errors.js';
import { probe } from './http.js';

export function createDocumentAdapter(request) {
  return {
    async upload({ permitId, type, filename, contentBase64 }) {
      const r = await request('POST', '/files', { body: { permitId, type, filename, contentBase64 } });
      if (!r || typeof r.docId !== 'string') throw new DownstreamBadResponse('documents', 'documents returned no docId');
      return r;
    },
    health: () => probe(request),
  };
}
