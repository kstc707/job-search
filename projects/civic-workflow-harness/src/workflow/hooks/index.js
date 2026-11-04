// Hook registry. config/workflow.json names hooks per event ("notify:fees_due" = hook `notify` with
// argument `fees_due`); unknown names fail at startup, not at the first submit.
import validateRequiredFields from './validateRequiredFields.js';
import checkParcelZoning from './checkParcelZoning.js';
import checkRequiredDocuments from './checkRequiredDocuments.js';
import advanceToFeeAssessment from './advanceToFeeAssessment.js';
import calculateFees from './calculateFees.js';
import notify from './notify.js';

const registry = { validateRequiredFields, checkParcelZoning, checkRequiredDocuments, advanceToFeeAssessment, calculateFees, notify };

export function resolveHooks(eventHooks) {
  const out = {};
  for (const [event, specs] of Object.entries(eventHooks)) {
    if (!/^(before|after)[A-Z]\w*$/.test(event)) throw new Error(`workflow.json: bad event name "${event}"`);
    out[event] = specs.map((spec) => {
      const [name, arg] = spec.split(':');
      const fn = registry[name];
      if (!fn) throw new Error(`workflow.json: unknown hook "${name}" on ${event}`);
      return { name: spec, run: (ctx) => fn(ctx, arg) };
    });
  }
  return out;
}
