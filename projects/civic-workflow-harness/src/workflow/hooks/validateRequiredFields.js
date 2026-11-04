import { ValidationError } from '../../errors.js';
import { getPath, isBlank } from '../../lib/util.js';

/** beforeSubmit: every field the permit type requires must be filled in. */
export default function validateRequiredFields(ctx) {
  const missing = ctx.permitType.requiredFields.filter((f) => isBlank(getPath(ctx.permit, f)));
  if (missing.length) {
    throw new ValidationError(`Missing required fields: ${missing.join(', ')}`, { status: 422, code: 'missing_fields', details: { missingFields: missing } });
  }
}
