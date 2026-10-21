/*
 * The fill run for one frame. background.js injects every content file into every frame of
 * the tab (iCIMS and embedded Greenhouse forms live in iframes), then calls
 * AutofillRun({profilePack, jobPack}) in each frame and collects the reports.
 *
 * Order: detect the ATS -> warn about things only the user can do (captcha, sign-in) ->
 * the adapter collects questions, the answer engine resolves each one, fillField applies it ->
 * outline filled fields (subtle) and unfilled required ones (red) -> report.
 * Nothing here ever clicks submit / next / apply, and form submissions are blocked while it runs.
 */
(function (root) {
  'use strict';
  const D = root.AutofillDom;
  const C = root.AutofillCollect;
  const A = root.AutofillAnswers;

  // A career-site page that only wraps an ATS form in an iframe: the iframe's own run fills it.
  const ATS_IFRAME = 'iframe#grnhse_iframe, iframe#icims_content_iframe, iframe[src*="greenhouse.io"], iframe[src*="icims.com"], '
    + 'iframe[src*="lever.co"], iframe[src*="ashbyhq.com"], iframe[src*="myworkdayjobs.com"], iframe[src*="smartrecruiters.com"]';
  const CAPTCHA = 'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], .g-recaptcha, .h-captcha, .cf-turnstile';

  function display(v) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      if (v.filename) return v.filename;
      if (v.year) return `${v.month ? String(v.month).padStart(2, '0') + '/' : ''}${v.year}`;
    }
    if (Array.isArray(v)) return v.join(', ');
    if (v === true) return 'checked';
    if (v === false) return 'unchecked';
    const s = String(v);
    return s.length > 80 ? s.slice(0, 77) + '...' : s;
  }

  const SKIP_REASON = {
    'ask-rule': 'ASK rule',
    'no-rule': 'no rule',
    'blank-rule': 'rule says leave blank',
    'no-file': 'no file in the packs',
    'no-option': 'no matching option',
  };

  function makeContext(input, adapter) {
    const profilePack = input.profilePack || {};
    const jobPack = input.jobPack || null;
    const files = {
      resume: (jobPack && jobPack.resume) || profilePack.defaultResume || null,
      cover_letter: (jobPack && jobPack.coverLetter) || null,
    };
    const bank = new A.AnswerBank(profilePack.profile || {}, profilePack.rules || [], files,
      jobPack ? jobPack.answers : null, { extras: true });
    const items = new Map();
    const ctx = {
      doc: document, adapter, bank, profile: profilePack.profile || {}, files, done: new WeakSet(),
      items,
      add(item) { items.set(item.key || `${item.label}|${items.size}`, item); },
      need(label, reason) { ctx.add({ key: 'notice:' + label, label, status: 'needs', reason, required: true, notice: true }); },
      info(label, reason) { ctx.add({ key: 'info:' + label, label, status: 'info', reason, notice: true }); },
      mark(el, kind) { D.highlight(D.visualOf(el), kind); },

      /** Resolve a question's fields with the answer engine and fill each one. */
      async answer(q) {
        for (const r of bank.plan([q])) await ctx.apply(r);
      },

      async apply(r) {
        const q = r.question;
        const f = r.field;
        const item = { key: `${q.label}|${f.type}|${f.name}`, label: q.label, required: !!q.required, source: r.source, note: r.note };
        if (r.status === 'fill') {
          let err;
          try { err = await C.fillField(q, f, r.value, adapter); } catch (e) { err = e.message; }
          if (err) Object.assign(item, { status: 'needs', reason: `could not fill: ${err}` });
          else Object.assign(item, { status: 'filled', value: display(f.shown !== undefined ? f.shown : r.value) });
        } else if (r.status === 'ask') {
          Object.assign(item, { status: 'needs', reason: `ASK rule: answer it yourself${r.note && r.note !== 'needs your answer' ? ' (' + r.note + ')' : ''}` });
        } else if ((r.status === 'missing' || r.status === 'no-option') && C.hasValue(f)) {
          // No approved answer, but the page already shows one (Workday's country phone code).
          Object.assign(item, { status: 'skipped', reason: 'kept the value already on the page' });
        } else if (r.status === 'missing') {
          Object.assign(item, { status: 'needs', reason: r.why === 'no-file' ? 'required file: no resume in the job or profile pack' : 'unknown required: no approved answer' });
        } else if (r.status === 'no-option') {
          Object.assign(item, { status: q.required ? 'needs' : 'skipped', reason: `no matching option: ${r.note}` });
        } else {
          Object.assign(item, { status: 'skipped', reason: r.why === 'years' ? r.note : (SKIP_REASON[r.why] || r.note || 'skipped') });
        }
        ctx.add(item);
        if (item.status === 'filled') ctx.mark(f.markEl || f.el, 'filled');
        else if (item.status === 'needs' || (q.required && !C.hasValue(f))) ctx.mark(f.markEl || f.el, 'needs');
      },

      /** Fill a profile value straight into a field (Workday work history / education). */
      async put(label, f, value) {
        const q = { label, required: false };
        const item = { key: `${label}|${f.type}`, label, required: false, source: 'profile' };
        let err;
        try { err = await C.fillField(q, f, value, adapter); } catch (e) { err = e.message; }
        Object.assign(item, err ? { status: 'needs', reason: `could not fill: ${err}` }
          : { status: 'filled', value: display(f.shown !== undefined ? f.shown : value) });
        ctx.add(item);
        ctx.mark(f.markEl || f.el, err ? 'needs' : 'filled');
        return !err;
      },

      /**
       * Collect, answer, repeat: answering one question can reveal another ("If yes, ...",
       * Workday's State after Country), so collect again up to three times.
       */
      async fillQuestions(collect, opts) {
        const o = opts || {};
        for (let pass = 0; pass < 3; pass++) {
          let qs = collect().filter((q) => q.el && !ctx.done.has(q.el));
          if (!qs.length) break;
          if (o.sort) qs = o.sort(qs);
          for (const q of qs) {
            ctx.done.add(q.el);
            await ctx.answer(q);
          }
          await D.sleep(250);
        }
      },
    };
    return ctx;
  }

  let running = false;

  root.AutofillRun = async function (input) {
    const adapter = root.AutofillAdapters.detect(location, document);
    const report = {
      frame: location.href, top: window === window.top, ats: adapter.id, adapter: adapter.name,
      page: '', items: [], ruleErrors: [], counts: { filled: 0, skipped: 0, needs: 0, info: 0 },
    };
    if (running) { report.error = 'a fill is already running in this frame'; return report; }
    running = true;
    D.blockSubmits(true);
    D.clearHighlights();
    const ctx = makeContext(input || {}, adapter);
    report.ruleErrors = ctx.bank.ruleErrors;
    try {
      report.page = adapter.page ? adapter.page(document) : '';
      if (D.deepQueryAll(document, CAPTCHA).length) ctx.need('Captcha', 'this page has a captcha: solve it yourself before submitting');
      if (adapter.notices) adapter.notices(ctx);
      if (adapter.id === 'generic' && document.querySelector(ATS_IFRAME)) {
        ctx.info('Embedded form', 'The application form is in an iframe; it was filled there, not on this wrapper page.');
      } else if (adapter.fill) await adapter.fill(ctx);
      else await ctx.fillQuestions(() => (adapter.collect ? adapter.collect(ctx) : C.collectGeneric(document)));
    } catch (e) {
      report.error = `${e.name}: ${e.message}`;
    } finally {
      // Late submit events (a framework reacting to our last change) are still blocked briefly.
      setTimeout(() => D.blockSubmits(false), 1500);
      running = false;
    }
    report.items = [...ctx.items.values()].map(({ key, ...rest }) => rest);
    for (const it of report.items) report.counts[it.status] = (report.counts[it.status] || 0) + 1;
    return report;
  };
})(globalThis);
