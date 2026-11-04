import { ValidationError } from '../../errors.js';

/**
 * beforeSubmit: look the parcel up in GIS and check zoning allows this permit type.
 * GIS errors are fatal here (submit is blocked, the draft is unchanged): approving work on an unverified
 * parcel is worse than asking the applicant to retry.
 */
export default async function checkParcelZoning(ctx) {
  const { permit, permitType } = ctx;
  const parcel = await ctx.adapters.gis.lookupParcel(permit.parcelId);
  if (!permitType.allowedZoning.includes(parcel.zoning)) {
    throw new ValidationError(`Zoning ${parcel.zoning} on parcel ${permit.parcelId} does not allow a ${permit.permitType} permit`, {
      status: 422,
      code: 'zoning_not_permitted',
      details: { zoning: parcel.zoning, allowedZoning: permitType.allowedZoning },
    });
  }
  permit.parcel = { zoning: parcel.zoning, district: parcel.district ?? null };
  if (ctx.features.floodZone) permit.floodZone = parcel.floodZone ?? null;
}
