// Typed errors. Every error the API can return maps to one HTTP status and a stable `code`,
// so clients (and tests) branch on `code`, never on message text.
export class AppError extends Error {
  constructor(message, { status = 500, code = 'internal_error', details } = {}) {
    super(message);
    this.name = new.target.name;
    this.status = status;
    this.code = code;
    if (details !== undefined) this.details = details;
  }
  toJSON() {
    return { code: this.code, message: this.message, ...(this.service ? { service: this.service } : {}), ...(this.details !== undefined ? { details: this.details } : {}) };
  }
}

export class ValidationError extends AppError {
  constructor(message, { status = 400, code = 'validation_error', details } = {}) { super(message, { status, code, details }); }
}
export class NotFoundError extends AppError {
  constructor(message) { super(message, { status: 404, code: 'not_found' }); }
}
export class ConflictError extends AppError {
  constructor(message, { code = 'conflict', details } = {}) { super(message, { status: 409, code, details }); }
}
export class UnauthorizedError extends AppError {
  constructor(message) { super(message, { status: 401, code: 'unauthorized' }); }
}
export class SchemaMismatchError extends AppError {
  constructor(message) { super(message, { status: 500, code: 'schema_mismatch' }); }
}

// Downstream (adapter) errors carry the service name.
export class DownstreamError extends AppError {
  constructor(service, message, { status, code, downstreamStatus, body } = {}) {
    super(message, { status, code });
    this.service = service;
    if (downstreamStatus !== undefined) this.downstreamStatus = downstreamStatus;
    if (body !== undefined) this.body = body;
  }
}
/** The service did not answer within the per-call timeout. Outcome unknown. */
export class DownstreamTimeout extends DownstreamError {
  constructor(service, message, extra = {}) { super(service, message, { ...extra, status: 504, code: 'downstream_timeout' }); }
}
/** Connection refused/reset or a 5xx: the call definitely did not succeed (or we must assume so). */
export class DownstreamUnavailable extends DownstreamError {
  constructor(service, message, extra = {}) { super(service, message, { ...extra, status: 503, code: 'downstream_unavailable' }); }
}
/** 2xx but the body was not parseable or not the expected shape. */
export class DownstreamBadResponse extends DownstreamError {
  constructor(service, message, extra = {}) { super(service, message, { ...extra, status: 502, code: 'downstream_bad_response' }); }
}
/** The service answered 4xx: it understood and refused. Adapters translate the expected ones. */
export class DownstreamRejected extends DownstreamError {
  constructor(service, message, extra = {}) { super(service, message, { ...extra, status: 502, code: 'downstream_rejected' }); }
}
