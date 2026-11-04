// Seed a live deployment with permits in several states, and record what they looked like, so smoke
// checks 5-7 can prove an upgrade or rollback did not lose or change them.
import { writeFileSync } from 'node:fs';

const PDF = Buffer.from('%PDF-1.4 seed').toString('base64');

export async function seed(baseUrl, seedFile) {
  const call = async (method, path, body) => {
    const r = await fetch(baseUrl + path, { method, headers: { 'content-type': 'application/json' }, body: body && JSON.stringify(body) });
    const json = await r.json();
    if (r.status >= 400) throw new Error(`seed ${method} ${path}: ${r.status} ${JSON.stringify(json)}`);
    return json;
  };
  const waitPaid = async (id) => {
    for (let i = 0; i < 100; i++) {
      if ((await call('GET', `/permits/${id}`)).status === 'paid') return;
      await new Promise((r) => setTimeout(r, 50));
    }
    throw new Error(`seed: ${id} never paid`);
  };
  const make = async (n, target) => {
    const p = await call('POST', '/permits', { permitType: 'building', applicant: { name: `Seed Applicant ${n}`, email: `seed${n}@example.org` }, parcelId: n % 2 ? 'P-1001' : 'P-1004', description: `Seeded permit ${n}`, valuation: 25000 * n, tags: ['seed'] });
    if (target === 'draft') return p.id;
    for (const type of ['site_plan', 'construction_drawings']) await call('POST', `/permits/${p.id}/documents`, { type, filename: `${type}.pdf`, contentBase64: PDF });
    await call('POST', `/permits/${p.id}/submit`);
    if (target === 'fees_assessed') return p.id;
    await call('POST', `/permits/${p.id}/payments`);
    await waitPaid(p.id);
    if (target === 'paid') return p.id;
    for (const action of ['start_review', 'approve', 'issue']) await call('POST', `/permits/${p.id}/transitions`, { action });
    if (target === 'issued') return p.id;
    await call('POST', `/permits/${p.id}/inspections`, { type: 'final', result: 'pass', inspector: 'Seed Inspector' });
    return p.id;
  };
  const targets = ['draft', 'fees_assessed', 'paid', 'issued', 'finaled'];
  const permits = [];
  for (const [i, t] of targets.entries()) {
    const id = await make(i + 1, t);
    const p = await call('GET', `/permits/${id}`);
    permits.push({ id, status: p.status, applicantName: p.applicant.name, valuation: p.valuation, invoiceTotalCents: p.invoice?.totalCents ?? null });
  }
  writeFileSync(seedFile, JSON.stringify({ createdAt: new Date().toISOString(), permits }, null, 2));
  return permits;
}
