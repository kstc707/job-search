/*
 * Greenhouse: hosted boards (job-boards.greenhouse.io, boards.greenhouse.io) and the embedded
 * form (#grnhse_app iframe, which is a greenhouse.io frame of its own).
 * Fields carry Greenhouse's names as ids (first_name, last_name, email, phone, resume,
 * question_123...), so the contact fields map by name exactly as in the cloud filler.
 * Dropdowns on the new boards are react-select comboboxes; location is a type-ahead.
 */
(function (root) {
  'use strict';
  const C = root.AutofillCollect;
  root.AutofillAdapters.register({
    id: 'greenhouse',
    name: 'Greenhouse',
    order: 30,
    host: /(^|\.)greenhouse\.io$/,
    sniff: (doc) => !!doc.querySelector('#application_form, #grnhse_app form, form[action*="greenhouse"], .application--form, #application-form #first_name'),
    page: () => 'application',
    collect(ctx) {
      const scope = ctx.doc.querySelector('#application-form, #application_form, form.application--form') || ctx.doc;
      return C.collectGeneric(scope);
    },
  });
})(globalThis);
