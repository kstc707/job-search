// Permit service: the use cases behind the REST API. Every write runs inside store.mutate(), so a
// thrown error (validation, invalid transition, downstream failure) commits nothing.
import { NotFoundError, ConflictError, ValidationError, UnauthorizedError, DownstreamTimeout } from './errors.js';
import { validatePermitFields, validateDocument, validateInspection, requireObject } from './workflow/validate.js';
import { verify } from './lib/signature.js';
import { randomUUID } from 'node:crypto';
import { pad, isBlank, isObject } from './lib/util.js';

// Ids sent to other systems as idempotency keys carry a random suffix. Store counters can rewind if a
// backup is restored; a key the provider has already seen would silently return the OLD charge/message.
const nonce = () => randomUUID().slice(0, 8);

const EVENT_TYPES = ['charge.pending', 'charge.succeeded', 'charge.failed'];
const EDITABLE = ['applicant', 'parcelId', 'description', 'valuation', 'tags'];

export function createService({ store, engine, adapters, config, features, webhookSecret, publicUrl, outbox, now = () => new Date().toISOString() }) {
  const wf = config.workflow;

  function enqueue(state, permit, template, extra = {}) {
    state.counters.message += 1;
    const sms = features.notifyChannel && permit.applicant.notifyChannel === 'sms';
    state.outbox.push({
      id: `msg-${pad(state.counters.message)}-${nonce()}`,
      permitId: permit.id,
      template,
      channel: sms ? 'sms' : 'email',
      to: sms ? permit.applicant.phone : permit.applicant.email,
      data: { permitId: permit.id, status: permit.status, totalCents: permit.invoice?.totalCents ?? null, ...extra },
      status: 'pending',
      attempts: 0,
      lastError: null,
      createdAt: now(),
    });
  }

  const ctxFor = (state) => ({ state, config, features, adapters, now, enqueueNotification: (p, t) => enqueue(state, p, t) });

  async function write(fn) {
    const result = await store.mutate(fn);
    if (store.read().outbox.some((e) => e.status === 'pending')) outbox.dispatch().catch(() => {});
    return result;
  }

  function need(state, id) {
    const p = state.permits[id];
    if (!p) throw new NotFoundError(`Permit ${id} not found`);
    return p;
  }

  const view = (p) => ({ ...p, allowedActions: engine.clientActions(p) });

  function closeReconciliation(state, key, resolution) {
    for (const r of state.reconciliation) {
      if (r.idempotencyKey === key && r.status === 'open') {
        r.status = 'closed';
        r.resolution = resolution;
        r.closedAt = now();
      }
    }
  }

  function openReconciliation(state, item) {
    state.counters.reconciliation += 1;
    state.reconciliation.push({ id: `REC-${pad(state.counters.reconciliation)}`, status: 'open', openedAt: now(), attempts: 0, ...item });
  }

  async function markPaid(state, p, ctx) {
    p.payment.status = 'succeeded';
    p.payment.paidAt = now();
    if (p.status === 'fees_assessed') await engine.apply(p, 'payment_received', ctx);
  }

  return {
    getPermit(id) {
      return view(need(store.read(), id));
    },

    listPermits({ status, tag } = {}) {
      return Object.values(store.read().permits)
        .filter((p) => (!status || p.status === status) && (!tag || (p.tags ?? []).includes(tag)))
        .map((p) => ({ id: p.id, permitType: p.permitType, status: p.status, createdAt: p.createdAt }));
    },

    createPermit(body) {
      const f = validatePermitFields(body, { workflow: wf, features });
      return write((s) => {
        s.counters.permit += 1;
        const id = `PRM-${pad(s.counters.permit)}`;
        const at = now();
        const p = {
          id,
          permitType: f.permitType,
          status: 'draft',
          applicant: f.applicant,
          parcelId: f.parcelId ?? null,
          description: f.description ?? null,
          valuation: f.valuation ?? null,
          tags: f.tags ?? [],
          documents: [],
          invoice: null,
          payment: null,
          inspections: [],
          history: [{ action: 'create', from: null, to: 'draft', at }],
          createdAt: at,
          updatedAt: at,
        };
        if (features.floodZone) p.floodZone = null;
        s.permits[id] = p;
        return view(p);
      });
    },

    updatePermit(id, body) {
      requireObject(body);
      const locked = Object.keys(body).filter((k) => !EDITABLE.includes(k));
      if (locked.length) throw new ValidationError(`Fields not editable: ${locked.join(', ')}`, { code: 'not_editable', details: { fields: locked } });
      return write((s) => {
        const p = need(s, id);
        if (p.status !== 'draft') throw new ConflictError(`Only draft permits can be edited (status is ${p.status})`, { code: 'not_draft' });
        const merged = {
          permitType: p.permitType,
          applicant: { ...p.applicant, ...(isObject(body.applicant) ? body.applicant : {}) },
          parcelId: body.parcelId !== undefined ? body.parcelId : p.parcelId,
          description: body.description !== undefined ? body.description : p.description,
          valuation: body.valuation !== undefined ? body.valuation : p.valuation,
          tags: body.tags ?? p.tags,
        };
        const f = validatePermitFields(merged, { workflow: wf, features });
        Object.assign(p, { applicant: f.applicant, parcelId: f.parcelId ?? null, description: f.description ?? null, valuation: f.valuation ?? null, tags: f.tags ?? [] });
        p.updatedAt = now();
        return view(p);
      });
    },

    submit(id) {
      return write(async (s) => {
        const p = need(s, id);
        await engine.apply(p, 'submit', ctxFor(s));
        return view(p);
      });
    },

    addDocument(id, body) {
      const d = validateDocument(body, { workflow: wf });
      return write(async (s) => {
        const p = need(s, id);
        if (p.status !== 'draft') throw new ConflictError(`Documents can only be added to draft permits (status is ${p.status})`, { code: 'not_draft' });
        const r = await adapters.documents.upload({ permitId: p.id, type: d.type, filename: d.filename, contentBase64: d.contentBase64 });
        const doc = { docId: r.docId, type: d.type, filename: d.filename, sizeBytes: d.sizeBytes, uploadedAt: now() };
        p.documents.push(doc);
        p.updatedAt = doc.uploadedAt;
        return { permit: view(p), document: doc };
      });
    },

    requestPayment(id) {
      return write(async (s) => {
        const p = need(s, id);
        if (p.status !== 'fees_assessed') throw new ConflictError(`Payment is only accepted for permits in fees_assessed (status is ${p.status})`, { code: 'invalid_transition' });
        // A second click while a charge is pending/unknown returns the same payment, never a second charge.
        if (p.payment && ['pending', 'unknown'].includes(p.payment.status)) return { permit: view(p), reused: true };
        const attempt = (p.payment?.attempt ?? 0) + 1;
        const idempotencyKey = `pay-${p.id}-${p.invoice.id}-${attempt}-${nonce()}`;
        const base = { idempotencyKey, attempt, amountCents: p.invoice.totalCents, currency: p.invoice.currency, lastSequence: 0, appliedEventIds: [], staleEventIds: [], requestedAt: now() };
        try {
          const charge = await adapters.payment.createCharge({
            permitId: p.id,
            amountCents: p.invoice.totalCents,
            currency: p.invoice.currency,
            idempotencyKey,
            callbackUrl: `${publicUrl()}/callbacks/payment`,
          });
          p.payment = { ...base, status: 'pending', chargeId: charge.id };
        } catch (e) {
          if (!(e instanceof DownstreamTimeout)) throw e;
          // Outcome unknown: the provider may or may not have created the charge. Do not retry blindly;
          // record it, answer the applicant, and let the callback or the reconciliation job decide.
          p.payment = { ...base, status: 'unknown', chargeId: null };
          openReconciliation(s, { permitId: p.id, idempotencyKey, reason: 'charge_timeout' });
        }
        p.updatedAt = now();
        return { permit: view(p), reused: false };
      });
    },

    async handlePaymentCallback(raw, signature) {
      if (!verify(webhookSecret, raw, signature)) throw new UnauthorizedError('Invalid or missing webhook signature');
      let ev;
      try {
        ev = JSON.parse(raw);
      } catch {
        throw new ValidationError('Callback body is not valid JSON', { code: 'malformed_json' });
      }
      if (!isObject(ev) || typeof ev.id !== 'string' || !EVENT_TYPES.includes(ev.type) || !Number.isInteger(ev.sequence) || typeof ev.idempotencyKey !== 'string') {
        throw new ValidationError('Callback is missing id, type, sequence or idempotencyKey', { code: 'invalid_event' });
      }
      return write(async (s) => {
        if (s.processedEvents[ev.id]) return { duplicate: true, eventId: ev.id };
        s.processedEvents[ev.id] = { type: ev.type, receivedAt: now() };
        const p = s.permits[ev.permitId];
        if (!p || !p.payment || p.payment.idempotencyKey !== ev.idempotencyKey) {
          s.orphanEvents.push({ eventId: ev.id, type: ev.type, permitId: ev.permitId ?? null, idempotencyKey: ev.idempotencyKey, receivedAt: now() });
          return { orphan: true, eventId: ev.id };
        }
        const pay = p.payment;
        if (ev.sequence <= pay.lastSequence) {
          pay.staleEventIds.push(ev.id); // arrived after a newer event for the same charge
          return { stale: true, eventId: ev.id };
        }
        pay.lastSequence = ev.sequence;
        pay.chargeId ??= ev.chargeId ?? null;
        pay.appliedEventIds.push(ev.id);
        closeReconciliation(s, pay.idempotencyKey, `resolved_by_callback:${ev.type}`);
        if (ev.type === 'charge.pending') {
          pay.status = 'pending';
        } else if (ev.type === 'charge.failed') {
          pay.status = 'failed';
          pay.failureReason = ev.reason ?? null;
          enqueue(s, p, 'payment_failed');
        } else if (ev.amountCents !== pay.amountCents) {
          pay.status = 'disputed';
          openReconciliation(s, { permitId: p.id, idempotencyKey: pay.idempotencyKey, reason: 'amount_mismatch', expectedCents: pay.amountCents, receivedCents: ev.amountCents });
          return { applied: false, reason: 'amount_mismatch', eventId: ev.id };
        } else {
          await markPaid(s, p, ctxFor(s));
        }
        p.updatedAt = now();
        return { applied: true, eventId: ev.id, status: p.status };
      });
    },

    /** Resolve charges whose creation timed out, by asking the provider what happened. */
    reconcile() {
      return write(async (s) => {
        const summary = { checked: 0, resolved: 0, stillOpen: 0 };
        for (const r of s.reconciliation.filter((x) => x.status === 'open' && x.reason === 'charge_timeout')) {
          summary.checked += 1;
          r.attempts += 1;
          let charge;
          try {
            charge = await adapters.payment.findCharge(r.idempotencyKey);
          } catch (e) {
            r.lastError = e.code;
            summary.stillOpen += 1;
            continue;
          }
          const p = s.permits[r.permitId];
          const pay = p?.payment?.idempotencyKey === r.idempotencyKey ? p.payment : null;
          r.status = 'closed';
          r.closedAt = now();
          summary.resolved += 1;
          if (!charge) {
            r.resolution = 'not_created';
            if (pay && pay.status === 'unknown') pay.status = 'not_created';
            continue;
          }
          r.resolution = `charge_${charge.status}`;
          if (!pay) continue;
          pay.chargeId = charge.id;
          pay.lastSequence = Math.max(pay.lastSequence, charge.sequence ?? 0);
          if (charge.status === 'succeeded') {
            if (charge.amountCents !== pay.amountCents) {
              pay.status = 'disputed';
              r.resolution = 'amount_mismatch';
            } else {
              await markPaid(s, p, ctxFor(s));
            }
          } else if (charge.status === 'failed') {
            pay.status = 'failed';
          } else {
            pay.status = 'pending';
          }
        }
        return summary;
      });
    },

    transition(id, body) {
      requireObject(body);
      const t = engine.transition(body.action);
      if (!t || t.system) throw new ValidationError(`"${body.action}" is not an action a client can request`, { code: 'unknown_action' });
      for (const field of t.requires ?? []) {
        if (isBlank(body[field])) throw new ValidationError(`${body.action} requires "${field}"`, { status: 422, code: 'missing_fields', details: { missingFields: [field] } });
      }
      return write(async (s) => {
        const p = need(s, id);
        if (body.reason !== undefined) p.decisionReason = String(body.reason);
        await engine.apply(p, body.action, ctxFor(s));
        return view(p);
      });
    },

    recordInspection(id, body) {
      const i = validateInspection(body, { workflow: wf });
      return write(async (s) => {
        const p = need(s, id);
        if (p.status !== 'issued') throw new ConflictError(`Inspections can only be recorded on issued permits (status is ${p.status})`, { code: 'invalid_transition' });
        s.counters.inspection += 1;
        const inspection = { id: `INS-${pad(s.counters.inspection)}`, ...i, at: now() };
        p.inspections.push(inspection);
        p.updatedAt = inspection.at;
        if (i.type === 'final' && i.result === 'pass') await engine.apply(p, 'final_inspection_passed', ctxFor(s));
        return { permit: view(p), inspection };
      });
    },

    outboxEntries({ permitId, status } = {}) {
      return store.read().outbox.filter((e) => (!permitId || e.permitId === permitId) && (!status || e.status === status));
    },
    reconciliationItems() {
      return store.read().reconciliation;
    },
  };
}
