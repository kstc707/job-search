import { ValidationError } from '../../errors.js';

/** beforeSubmit: required documents for the type, plus flood-zone extras (schema 2+). */
export default function checkRequiredDocuments(ctx) {
  const { permit, permitType, config, features } = ctx;
  const required = [...permitType.requiredDocuments];
  const fz = config.workflow.floodZones;
  if (features.floodZone && fz.highRisk.includes(permit.floodZone)) required.push(...fz.extraDocuments);
  const have = new Set(permit.documents.map((d) => d.type));
  const missing = [...new Set(required)].filter((t) => !have.has(t));
  if (missing.length) {
    throw new ValidationError(`Missing required documents: ${missing.join(', ')}`, { status: 422, code: 'missing_documents', details: { missingDocuments: missing } });
  }
}
