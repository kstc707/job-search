/*
 * SmartRecruiters: the one-click apply form is built from web components (spl-*, oc-*), so the
 * generic collector walks open shadow roots (AutofillDom.deepQueryAll).
 */
(function (root) {
  'use strict';
  const C = root.AutofillCollect;
  root.AutofillAdapters.register({
    id: 'smartrecruiters',
    name: 'SmartRecruiters',
    order: 41,
    host: /(^|\.)smartrecruiters\.com$/,
    sniff: (doc) => !!doc.querySelector('oc-oneclick-form, spl-form-field, [data-test="application-form"]'),
    page: () => (/oneclick-ui|apply/.test(location.pathname) ? 'apply' : ''),
    collect: (ctx) => C.collectGeneric(ctx.doc),
  });
})(globalThis);
