// GIS adapter: parcel lookup (zoning, district, flood zone). Read-only, so retried on 5xx and timeouts.
import { DownstreamRejected, DownstreamBadResponse, ValidationError } from '../errors.js';
import { probe } from './http.js';

export function createGisAdapter(request) {
  return {
    async lookupParcel(parcelId) {
      let parcel;
      try {
        parcel = await request('GET', `/parcels/${encodeURIComponent(parcelId)}`);
      } catch (e) {
        if (e instanceof DownstreamRejected && e.downstreamStatus === 404) {
          throw new ValidationError(`Parcel ${parcelId} does not exist in the GIS parcel layer`, { status: 422, code: 'unknown_parcel' });
        }
        throw e;
      }
      if (!parcel || parcel.parcelId !== parcelId || typeof parcel.zoning !== 'string') {
        throw new DownstreamBadResponse('gis', 'gis returned a parcel record without parcelId/zoning');
      }
      return parcel;
    },
    health: () => probe(request),
  };
}
