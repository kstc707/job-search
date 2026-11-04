import { calculateInvoice } from '../fees.js';

/** beforeAssessFees: build the invoice from config/fees.json. */
export default function calculateFees(ctx) {
  ctx.permit.invoice = calculateInvoice(ctx.permit, ctx.config.fees, `INV-${ctx.permit.id.slice(4)}`);
}
