/*
 * Everything else: label -> input pairs found by label[for], aria-labelledby, aria-label,
 * nearest text and placeholder (AutofillCollect.collectGeneric).
 * The named systems below have no special markup worth a dedicated reader yet; they are listed
 * so the popup says which system it saw, and they use the generic reader.
 */
(function (root) {
  'use strict';
  const C = root.AutofillCollect;
  const R = root.AutofillAdapters;
  const generic = (id, name, host, order) => R.register({
    id, name, host, order,
    page: () => '',
    notices(ctx) {
      const pw = ctx.doc.querySelector('input[type="password"]');
      if (pw && pw.getClientRects().length) ctx.need('Account', 'This page asks for a password: sign in or create the account yourself.');
    },
    collect: (ctx) => C.collectGeneric(ctx.doc),
  });
  generic('paylocity', 'Paylocity (generic reader)', /(^|\.)paylocity\.com$/, 60);
  generic('ukg', 'UKG / UltiPro (generic reader)', /(^|\.)(ultipro|ukg)\.(com|net)$/, 61);
  generic('dayforce', 'Dayforce (generic reader)', /(^|\.)dayforcehcm\.com$/, 62);
  generic('adp', 'ADP (generic reader)', /(^|\.)adp\.com$/, 63);
  generic('bamboohr', 'BambooHR (generic reader)', /(^|\.)bamboohr\.com$/, 64);
  generic('generic', 'Generic', null, 99);
})(globalThis);
