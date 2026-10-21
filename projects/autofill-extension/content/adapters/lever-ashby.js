/*
 * Lever and Ashby, read the same way as auto_apply/filler/domform.py: one question per
 * container, label from the system's label element, "required" from its marker.
 * Lever's location is a type-ahead with a hidden selectedLocation input; Ashby's yes/no
 * questions are two buttons.
 */
(function (root) {
  'use strict';
  const C = root.AutofillCollect;
  // Same selectors as PROFILES in domform.py.
  const PROFILES = {
    lever: { container: 'li.application-question, div.application-question', label: '.application-label', required: '.required' },
    ashby: { container: '.ashby-application-form-field-entry', label: 'label.ashby-application-form-question-title', requiredLabelClass: '_required' },
  };
  root.AutofillAdapters.register({
    id: 'lever',
    name: 'Lever',
    order: 20,
    host: /(^|\.)lever\.co$/,
    sniff: (doc) => !!doc.querySelector('.application-question') && !!doc.querySelector('#btn-submit, .application-form, form[action*="lever"]'),
    page: () => (location.pathname.endsWith('/apply') ? 'apply' : ''),
    collect: (ctx) => C.collectContainers(ctx.doc, PROFILES.lever),
  });
  root.AutofillAdapters.register({
    id: 'ashby',
    name: 'Ashby',
    order: 21,
    host: /(^|\.)ashbyhq\.com$/,
    sniff: (doc) => !!doc.querySelector('.ashby-application-form-field-entry'),
    page: () => (location.pathname.endsWith('/application') ? 'application' : ''),
    notices(ctx) {
      if (!ctx.doc.querySelector('.ashby-application-form-field-entry') && /ashbyhq/.test(location.hostname)) {
        ctx.info('Ashby', 'Open the Application tab first, then press Fill.');
      }
    },
    collect: (ctx) => C.collectContainers(ctx.doc, PROFILES.ashby),
  });
})(globalThis);
