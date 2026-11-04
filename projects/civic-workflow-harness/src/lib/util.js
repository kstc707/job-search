export const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
export const isBlank = (v) => v === undefined || v === null || (typeof v === 'string' && v.trim() === '');
export function getPath(obj, path) {
  return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
export const pad = (n, width = 6) => String(n).padStart(width, '0');
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const PHONE_RE = /^\+?[0-9]{10,15}$/;
export const PARCEL_RE = /^P-\d{4}$/;
