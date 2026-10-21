/*
 * Oracle Cloud HCM "Candidate Experience" (…oraclecloud.com/hcmUI/CandidateExperience/…).
 * Questions sit in .input-row containers with an .input-row__label; yes/no questions are two
 * pill buttons; lists are comboboxes (Oracle JET). Fields outside those rows fall back to the
 * generic collector. The email + one-time code step before the form is left to the user.
 */
(function (root) {
  'use strict';
  const C = root.AutofillCollect;
  root.AutofillAdapters.register({
    id: 'oracle',
    name: 'Oracle Cloud HCM',
    order: 42,
    host: /(^|\.)oraclecloud\.com$/,
    sniff: (doc) => !!doc.querySelector('.apply-flow, [class*="apply-flow-"], .input-row__label'),
    page: (doc) => {
      const step = doc.querySelector('.apply-flow-pagination__step--active, [aria-current="step"]');
      return step ? (step.innerText || '').trim() : '';
    },
    notices(ctx) {
      const code = ctx.doc.querySelector('input[autocomplete="one-time-code"], input[name*="pin" i], input[id*="pin" i]');
      if (code && code.getClientRects().length) ctx.need('Verification code', 'Enter the code Oracle emailed you yourself, then press Fill.');
    },
    collect(ctx) {
      const rows = C.collectContainers(ctx.doc, { container: '.input-row', label: '.input-row__label, label' });
      const covered = rows.map((q) => q.box).filter(Boolean);
      return rows.concat(C.collectGeneric(ctx.doc, { exclude: covered }));
    },
  });
})(globalThis);
