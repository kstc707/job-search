// Fee calculation, in integer cents (no floating-point money).
export function calculateInvoice(permit, feeSchedule, invoiceId) {
  const rule = feeSchedule.types[permit.permitType];
  if (!rule) throw new Error(`No fee rule for permit type ${permit.permitType}`);
  const lines = [{ code: 'BASE', description: `${permit.permitType} permit base fee`, amountCents: rule.baseCents }];
  if (rule.perThousandValuationCents) {
    const thousands = Math.ceil((permit.valuation ?? 0) / 1000);
    lines.push({ code: 'VALUATION', description: `${thousands} x $1,000 of valuation`, amountCents: thousands * rule.perThousandValuationCents });
  }
  let subtotal = lines.reduce((sum, l) => sum + l.amountCents, 0);
  if (rule.minimumCents && subtotal < rule.minimumCents) {
    lines.push({ code: 'MINIMUM', description: 'Adjustment to minimum permit fee', amountCents: rule.minimumCents - subtotal });
    subtotal = rule.minimumCents;
  }
  const tech = Math.round((subtotal * feeSchedule.technologyFeePercent) / 100);
  lines.push({ code: 'TECH', description: `Technology fee (${feeSchedule.technologyFeePercent}%)`, amountCents: tech });
  return { id: invoiceId, currency: feeSchedule.currency, lines, totalCents: subtotal + tech };
}
