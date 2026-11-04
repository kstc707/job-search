// v1.1.0: permits carry the GIS flood zone (high-risk zones need an elevation certificate) and
// applicants choose email or SMS notifications.
//
// down() keeps every permit, including ones created after the upgrade. It removes the v1.1 fields
// (v1.0 code does not know them) but archives their values, so re-running up() restores them.
// Pending SMS messages are re-addressed to email because v1.0 only sends email.
export const version = 2;
export const description = 'Permit floodZone + applicant notifyChannel';

export function up(state) {
  const s = structuredClone(state);
  const archive = s.archive002 ?? {};
  for (const p of Object.values(s.permits)) {
    const saved = archive[p.id];
    p.floodZone = saved ? saved.floodZone : null; // null = not yet looked up; set on submit
    p.applicant.notifyChannel = saved ? saved.notifyChannel : 'email';
    if (saved?.phone !== undefined) p.applicant.phone = saved.phone;
  }
  for (const m of s.outbox) {
    const saved = archive[`outbox:${m.id}`];
    if (saved) Object.assign(m, saved);
  }
  delete s.archive002;
  return s;
}

export function down(state) {
  const s = structuredClone(state);
  const archive = {};
  for (const p of Object.values(s.permits)) {
    archive[p.id] = { floodZone: p.floodZone ?? null, notifyChannel: p.applicant.notifyChannel ?? 'email', ...(p.applicant.phone !== undefined ? { phone: p.applicant.phone } : {}) };
    delete p.floodZone;
    delete p.applicant.notifyChannel;
  }
  for (const m of s.outbox) {
    if (m.status === 'pending' && m.channel === 'sms') {
      const p = s.permits[m.permitId];
      archive[`outbox:${m.id}`] = { channel: m.channel, to: m.to };
      m.channel = 'email';
      m.to = p?.applicant.email ?? m.to;
    }
  }
  s.archive002 = archive;
  return s;
}
