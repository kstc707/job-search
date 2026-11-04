/** afterSubmit: a submitted permit goes straight to fee assessment. */
export default async function advanceToFeeAssessment(ctx) {
  await ctx.apply('assess_fees');
}
