// Input validation for permit create/patch, documents and inspections. Field-level errors are
// collected so the client gets every problem in one 400, not one per round trip.
import { ValidationError } from '../errors.js';
import { isObject, isBlank, EMAIL_RE, PHONE_RE, PARCEL_RE } from '../lib/util.js';

const present = (v) => !isBlank(v);

export function requireObject(body) {
  if (!isObject(body)) throw new ValidationError('Request body must be a JSON object', { code: 'invalid_body' });
  return body;
}

/** Validates and returns the clean permit fields. `features` gates v1.1 fields. */
export function validatePermitFields(body, { workflow, features }) {
  requireObject(body);
  const errors = [];
  const err = (field, message) => errors.push({ field, message });

  if (isBlank(body.permitType)) err('permitType', 'is required');
  else if (!workflow.permitTypes[body.permitType]) err('permitType', `must be one of: ${Object.keys(workflow.permitTypes).join(', ')}`);

  const a = body.applicant;
  const applicant = {};
  if (!isObject(a)) err('applicant', 'is required');
  else {
    if (isBlank(a.email)) err('applicant.email', 'is required');
    else if (typeof a.email !== 'string' || !EMAIL_RE.test(a.email)) err('applicant.email', 'is not a valid email address');
    else applicant.email = a.email.trim();
    if (present(a.name)) {
      if (typeof a.name !== 'string' || a.name.length > 200) err('applicant.name', 'must be a string of at most 200 characters');
      else applicant.name = a.name.trim();
    }
    if (present(a.phone)) {
      if (typeof a.phone !== 'string' || !PHONE_RE.test(a.phone)) err('applicant.phone', 'must be 10-15 digits, optionally starting with +');
      else applicant.phone = a.phone;
    }
    if (features.notifyChannel) {
      const ch = present(a.notifyChannel) ? a.notifyChannel : 'email';
      if (!['email', 'sms'].includes(ch)) err('applicant.notifyChannel', 'must be "email" or "sms"');
      else if (ch === 'sms' && !applicant.phone && !errors.some((e) => e.field === 'applicant.phone')) err('applicant.phone', 'is required when notifyChannel is "sms"');
      applicant.notifyChannel = ch;
    }
  }

  const out = { permitType: body.permitType, applicant };
  if (present(body.parcelId)) {
    if (typeof body.parcelId !== 'string' || !PARCEL_RE.test(body.parcelId)) err('parcelId', 'must look like P-1234');
    else out.parcelId = body.parcelId;
  }
  if (present(body.description)) {
    if (typeof body.description !== 'string' || body.description.length > 2000) err('description', 'must be a string of at most 2000 characters');
    else out.description = body.description.trim();
  }
  if (body.valuation !== undefined && body.valuation !== null) {
    if (typeof body.valuation !== 'number' || !Number.isFinite(body.valuation) || body.valuation < 0) err('valuation', 'must be a non-negative number');
    else out.valuation = body.valuation;
  }
  if (body.tags !== undefined) {
    if (!Array.isArray(body.tags) || !body.tags.every((t) => typeof t === 'string')) err('tags', 'must be an array of strings');
    else out.tags = body.tags;
  }
  if (errors.length) throw new ValidationError('Invalid permit fields', { code: 'invalid_fields', details: { errors } });
  return out;
}

export function validateDocument(body, { workflow }) {
  requireObject(body);
  const errors = [];
  if (!workflow.documentTypes.includes(body.type)) errors.push({ field: 'type', message: `must be one of: ${workflow.documentTypes.join(', ')}` });
  if (typeof body.filename !== 'string' || body.filename.trim() === '' || body.filename.length > 200) errors.push({ field: 'filename', message: 'is required (max 200 characters)' });
  let sizeBytes = 0;
  if (typeof body.contentBase64 !== 'string' || body.contentBase64 === '' || !/^[A-Za-z0-9+/]+={0,2}$/.test(body.contentBase64)) {
    errors.push({ field: 'contentBase64', message: 'is required and must be base64' });
  } else {
    sizeBytes = Buffer.from(body.contentBase64, 'base64').length;
    if (sizeBytes > workflow.maxDocumentBytes) errors.push({ field: 'contentBase64', message: `exceeds ${workflow.maxDocumentBytes} bytes` });
  }
  if (errors.length) throw new ValidationError('Invalid document', { code: 'invalid_fields', details: { errors } });
  return { type: body.type, filename: body.filename.trim(), contentBase64: body.contentBase64, sizeBytes };
}

export function validateInspection(body, { workflow }) {
  requireObject(body);
  const errors = [];
  if (!workflow.inspectionTypes.includes(body.type)) errors.push({ field: 'type', message: `must be one of: ${workflow.inspectionTypes.join(', ')}` });
  if (!['pass', 'fail'].includes(body.result)) errors.push({ field: 'result', message: 'must be "pass" or "fail"' });
  if (isBlank(body.inspector) || typeof body.inspector !== 'string') errors.push({ field: 'inspector', message: 'is required' });
  if (errors.length) throw new ValidationError('Invalid inspection', { code: 'invalid_fields', details: { errors } });
  return { type: body.type, result: body.result, inspector: body.inspector.trim(), notes: typeof body.notes === 'string' ? body.notes : null };
}
