/*
 * iCIMS: the form is an iframe (#icims_content_iframe, ...icims.com/...&in_iframe=1) inside the
 * company's career page. background.js injects into every frame, and this adapter is picked
 * by the iframe's own icims.com hostname (or its iCIMS_* class names).
 * Fields are plain inputs and selects with <label for>; the generic collector reads them.
 */
(function (root) {
  'use strict';
  const C = root.AutofillCollect;
  root.AutofillAdapters.register({
    id: 'icims',
    name: 'iCIMS',
    order: 40,
    host: /(^|\.)icims\.com$/,
    sniff: (doc) => !!doc.querySelector('[class*="iCIMS_"], #iCIMS_MainWrapper, form[action*="icims"]'),
    page: (doc) => {
      const m = /[?&]mode=([a-z_]+)/i.exec(location.search);
      return m ? m[1] : (doc.querySelector('iframe#icims_content_iframe') ? 'wrapper (form is in the iframe)' : '');
    },
    notices(ctx) {
      const pw = ctx.doc.querySelector('input[type="password"]');
      if (pw && pw.getClientRects().length) ctx.need('iCIMS account', 'Sign in or create your iCIMS account yourself, then press Fill.');
    },
    collect(ctx) {
      const scope = ctx.doc.querySelector('#iCIMS_MainWrapper form, form#cp_form, form[name="cp_form"]') || ctx.doc;
      return C.collectGeneric(scope);
    },
  });
})(globalThis);
