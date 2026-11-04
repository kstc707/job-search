// Config-driven state machine. Transitions and the hooks that run around them come from
// config/workflow.json. A transition with event "Submit" runs the `beforeSubmit` hooks (any of which
// may throw to block it), changes the status, appends history, then runs the `afterSubmit` hooks.
import { ValidationError, ConflictError } from '../errors.js';

export function createEngine(workflow, hooks) {
  const byAction = new Map(workflow.transitions.map((t) => [t.action, t]));
  for (const t of workflow.transitions) {
    for (const s of [...t.from, t.to]) {
      if (!workflow.states.includes(s)) throw new Error(`workflow.json: transition ${t.action} uses unknown state ${s}`);
    }
  }

  async function apply(permit, action, ctx) {
    const t = byAction.get(action);
    if (!t) throw new ValidationError(`Unknown action "${action}"`, { code: 'unknown_action' });
    if (!t.from.includes(permit.status)) {
      throw new ConflictError(`Cannot ${action} a permit in status "${permit.status}"`, {
        code: 'invalid_transition',
        details: { status: permit.status, allowedFrom: t.from, allowedActions: clientActions(permit) },
      });
    }
    const hctx = {
      ...ctx,
      permit,
      transition: t,
      permitType: workflow.permitTypes[permit.permitType],
      apply: (next) => apply(permit, next, ctx),
    };
    for (const h of hooks[`before${t.event}`] ?? []) await h.run(hctx);
    const from = permit.status;
    const at = ctx.now();
    permit.status = t.to;
    permit.history.push({ action, from, to: t.to, at });
    permit.updatedAt = at;
    for (const h of hooks[`after${t.event}`] ?? []) await h.run(hctx);
    return permit;
  }

  function clientActions(permit) {
    return workflow.transitions.filter((t) => !t.system && t.from.includes(permit.status)).map((t) => t.action);
  }

  return { apply, clientActions, transition: (action) => byAction.get(action) };
}
