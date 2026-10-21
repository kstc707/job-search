/*
 * Workday (…myworkdayjobs.com, …myworkday.com).
 *
 * The apply flow is several pages (My Information, My Experience, Application Questions,
 * Voluntary Disclosures, Self Identify, Review). Fill covers the page on screen only: the user
 * checks it, clicks "Save and Continue" and presses Fill again on the next page.
 *
 * Every question is a container [data-automation-id="formField-…"] holding a <label> or
 * <legend> and one control: a text box, a dropdown button (button[aria-haspopup=listbox] that
 * opens a [role=listbox] of [role=option]s), a search prompt (multiselect input: type, Enter,
 * pick a promptOption), radios, checkboxes, or a date split into month / year inputs.
 *
 * "My Experience" holds repeating sections (Work Experience 1..n, Education 1..n). They are
 * filled from the profile's workExperience / education lists, clicking the section's "Add"
 * button for each missing entry. The resume goes into the file-upload input.
 */
(function (root) {
  'use strict';
  const D = root.AutofillDom;
  const C = root.AutofillCollect;
  const A = root.AutofillAnswers;
  const FF = '[data-automation-id^="formField-"]';

  function boxLabel(box) {
    let el = box.querySelector('legend');
    if (!el) {
      el = [...box.querySelectorAll('label')].find((l) => {
        const target = l.htmlFor && D.byIdInRoot(l, l.htmlFor);
        return !target || !/^(radio|checkbox)$/.test(target.type);
      });
    }
    if (!el) {
      const boxes = box.querySelectorAll('input[type="checkbox"]');
      if (boxes.length === 1) el = D.labelElementFor(boxes[0]);
    }
    if (!el) el = box.querySelector('[data-automation-id="richText"], [id$="-label"]');
    const raw = el ? D.ownText(el) : (D.textChunks(box)[0] || '');
    return { label: D.cleanLabel(raw), raw };
  }

  /** The control inside one formField container, as a field the answer engine understands. */
  function wdField(box, label) {
    const month = box.querySelector('[data-automation-id="dateSectionMonth-input"]');
    const year = box.querySelector('[data-automation-id="dateSectionYear-input"]');
    if (month || year) {
      return { type: 'date', name: box.getAttribute('data-automation-id') || '', el: year || month, markEl: box, parts: { month, year }, options: null };
    }
    const prompt = box.querySelector('[data-automation-id="multiselectInputContainer"] input, input[data-uxi-widget-type="selectinput"], input[data-automation-id="searchBox"]');
    if (prompt) return { type: 'combobox', name: C.nameOf(prompt), el: prompt, options: null, enter: true };
    const dd = box.querySelector('button[aria-haspopup="listbox"]');
    if (dd) return { type: 'combobox', name: C.nameOf(dd), el: dd, options: null };
    const radios = [...box.querySelectorAll('input[type="radio"]')];
    if (radios.length) return C.groupField(radios);
    const boxes = [...box.querySelectorAll('input[type="checkbox"]')];
    if (boxes.length === 1) {
      return { type: 'checkbox', name: C.nameOf(boxes[0]), el: boxes[0], options: [{ label: C.optionLabel(boxes[0]), el: boxes[0] }] };
    }
    if (boxes.length > 1) return C.groupField(boxes);
    const other = box.querySelector('input[type="file"], textarea, select, input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])');
    if (other && !other.disabled && !(other.tagName === 'INPUT' && other.readOnly)) return C.singleField(other, label);
    return null;
  }

  function collectWorkday(doc, exclude) {
    const out = [];
    for (const box of D.deepQueryAll(doc, FF)) {
      if (exclude.some((x) => x.contains(box))) continue;
      if (box.parentElement && box.parentElement.closest(FF)) continue;
      if (!D.isVisible(box)) continue;
      const { label, raw } = boxLabel(box);
      if (!label) continue;
      const f = wdField(box, label);
      if (!f) continue;
      const required = D.isRequired(f.el, raw, null) || !!box.querySelector('abbr[title="required" i], [aria-required="true"], [required]');
      out.push({ label, required, fields: [f], el: f.el, box });
    }
    // The resume upload sits in its own section, outside any formField.
    for (const input of doc.querySelectorAll('input[type="file"]')) {
      if (input.closest(FF) || exclude.some((x) => x.contains(input))) continue;
      const sec = input.closest('[data-automation-id*="resume" i], [data-automation-id*="attachment" i], section, [role="group"]');
      const head = sec && sec.querySelector('h2, h3, h4, legend, label');
      const text = head ? D.ownText(head) : '';
      const label = /cover/i.test(text) ? 'Cover Letter' : 'Resume/CV';
      out.push({ label, required: D.markedRequired(text), fields: [C.singleField(input, label)], el: input });
    }
    return out;
  }

  // Country changes which address fields Workday shows, so it goes first.
  const countryFirst = (qs) => [...qs].sort((a, b) => (/^country$/i.test(b.label) ? 1 : 0) - (/^country$/i.test(a.label) ? 1 : 0));

  // ---------- repeating sections ----------

  const KINDS = {
    work: {
      title: 'Work Experience',
      heading: /^work experience$/i,
      entryId: /^workExperience-\d+$/,
      entryHeading: /^work experience \d+$/i,
      list: (p) => p.workExperience || [],
      fields: [
        { keys: ['jobTitle'], label: /^job title/i, name: 'Job Title', value: (w) => w.role },
        { keys: ['company'], label: /^company/i, name: 'Company', value: (w) => w.company },
        { keys: ['location'], label: /^location/i, name: 'Location', value: (w) => w.location },
        { keys: ['currentlyWorkHere'], label: /currently work here/i, name: 'I currently work here', value: (w) => !!w.isCurrentRole },
        { keys: ['startDate'], label: /^from/i, name: 'From', value: (w) => A.parseDate(w.startDate) },
        { keys: ['endDate'], label: /^to\b/i, name: 'To', value: (w) => (w.isCurrentRole ? undefined : A.parseDate(w.endDate)) },
      ],
    },
    edu: {
      title: 'Education',
      heading: /^education$/i,
      entryId: /^education-\d+$/,
      entryHeading: /^education \d+$/i,
      list: (p) => p.education || [],
      fields: [
        { keys: ['school', 'schoolName'], label: /school|university/i, name: 'School or University', value: (e) => e.university },
        { keys: ['degree'], label: /^degree/i, name: 'Degree', value: (e) => (e.degree ? A.degreeAlternatives(e.degree) : undefined) },
        { keys: ['fieldOfStudy', 'field-of-study'], label: /field of study|major/i, name: 'Field of Study', value: (e) => e.major },
        { keys: ['gradeAverage', 'gpa', 'overallResult'], label: /gpa|overall result|grade average/i, name: 'Overall Result (GPA)', value: (e) => e.gpa },
        { keys: ['firstYearAttended', 'startDate'], label: /^from/i, name: 'From', value: (e) => A.parseDate(e.startDate) },
        { keys: ['lastYearAttended', 'endDate'], label: /^to\b/i, name: 'To (Actual or Expected)', value: (e) => A.parseDate(e.endDate) },
      ],
    },
  };

  function sectionOf(doc, k) {
    for (const g of doc.querySelectorAll('[role="group"][aria-labelledby]')) {
      const h = D.byIdInRoot(g, g.getAttribute('aria-labelledby'));
      if (h && k.heading.test(D.ownText(h).trim())) return g;
    }
    for (const h of doc.querySelectorAll('h2, h3, h4')) {
      if (k.heading.test(D.ownText(h).trim())) return h.closest('[role="group"], section') || h.parentElement;
    }
    return null;
  }

  function entriesOf(section, k) {
    let es = [...section.querySelectorAll('[data-automation-id]')].filter((e) => k.entryId.test(e.getAttribute('data-automation-id')));
    if (!es.length) {
      es = [...section.querySelectorAll('[role="group"][aria-labelledby]')].filter((g) => {
        const h = D.byIdInRoot(g, g.getAttribute('aria-labelledby'));
        return h && k.entryHeading.test(D.ownText(h).trim());
      });
    }
    return es;
  }

  function addButton(section, entries) {
    return [...section.querySelectorAll('button')].find((b) => !entries.some((e) => e.contains(b))
      && (b.getAttribute('data-automation-id') === 'add-button' || /^add( another)?$/i.test((b.innerText || '').trim())));
  }

  function findBox(entry, spec) {
    for (const key of spec.keys) {
      const box = entry.querySelector(`[data-automation-id="formField-${key}"]`);
      if (box) return box;
    }
    for (const key of spec.keys) {
      const c = entry.querySelector(`[data-automation-id="${key}"], [id$="--${key}"], [name="${key}"]`);
      if (c) return c.closest(FF) || c.parentElement;
    }
    return [...entry.querySelectorAll(FF)].find((b) => spec.label.test(boxLabel(b).label)) || null;
  }

  function fmtDate(d) {
    return d.month ? `${String(d.month).padStart(2, '0')}/${d.year}` : String(d.year);
  }

  async function fillEntry(ctx, entry, data, k, title) {
    for (const spec of k.fields) {
      let v = spec.value(data);
      if (v === undefined || v === null || v === '') continue;
      if (typeof v === 'object' && !Array.isArray(v) && v.year == null) continue;
      const box = findBox(entry, spec);
      if (!box || !D.isVisible(box)) continue;
      const f = wdField(box, spec.name);
      if (!f) continue;
      if (f.type === 'input_text' || f.type === 'textarea') {
        v = Array.isArray(v) ? v[0] : typeof v === 'object' ? fmtDate(v) : String(v);
      } else if (f.type === 'combobox') {
        v = Array.isArray(v) ? v : [String(v)];
      } else if (f.type === 'native_select') {
        const hit = A.pickOption(Array.isArray(v) ? v : [String(v)], f.options);
        if (!hit) { ctx.add({ label: `${title} › ${spec.name}`, status: 'needs', reason: `no matching option for '${Array.isArray(v) ? v[0] : v}'` }); continue; }
        v = hit;
      } else if (f.type === 'checkbox') {
        v = !!v;
      }
      await ctx.put(`${title} › ${spec.name}`, f, v);
      await D.sleep(60);
    }
  }

  async function fillRepeating(ctx, section, k) {
    const items = k.list(ctx.profile);
    if (!items.length) return;
    const want = Math.min(items.length, 10);
    let entries = entriesOf(section, k);
    while (entries.length < want) {
      const b = addButton(section, entries);
      if (!b) break;
      const before = entries.length;
      try { D.clickEl(b); } catch (e) { break; }
      const grown = await D.waitFor(() => entriesOf(section, k).length > before, 3000);
      entries = entriesOf(section, k);
      if (!grown) break;
    }
    const n = Math.min(want, entries.length);
    for (let i = 0; i < n; i++) await fillEntry(ctx, entries[i], items[i], k, `${k.title} ${i + 1}`);
    if (items.length > n) ctx.need(k.title, `${items.length - n} more in your profile than the page holds: add them yourself`);
    if (entries.length > items.length) {
      ctx.need(`${k.title} ${items.length + 1}+`, 'not in your profile (from resume parsing?): check or delete these entries');
    }
  }

  root.AutofillAdapters.register({
    id: 'workday',
    name: 'Workday',
    order: 10,
    host: /(^|\.)myworkdayjobs\.com$|(^|\.)myworkday\.com$|(^|\.)workday\.com$/,
    sniff: (doc) => !!doc.querySelector('[data-automation-id^="applyFlow"], [data-automation-id="formField-legalNameSection_firstName"]')
      || doc.querySelectorAll(FF).length >= 4,
    page(doc) {
      const p = [...doc.querySelectorAll('[data-automation-id^="applyFlow"][data-automation-id$="Page"]')]
        .find((e) => e.getAttribute('data-automation-id') !== 'applyFlowPage');
      const step = doc.querySelector('[data-automation-id="progressBarActiveStep"]');
      return [p && p.getAttribute('data-automation-id'), step && (step.innerText || '').trim().replace(/\s+/g, ' ')].filter(Boolean).join(' · ');
    },
    notices(ctx) {
      const doc = ctx.doc;
      const pw = doc.querySelector('input[type="password"]');
      if (doc.querySelector('[data-automation-id="signInContent"], [data-automation-id="createAccountPage"]') || (pw && pw.getClientRects().length)) {
        ctx.need('Workday account', 'Sign in or create your account yourself (and confirm the verification email), then press Fill on each page.');
      }
      if (doc.querySelector('[data-automation-id="applyManually"], [data-automation-id="autofillWithResume"]')) {
        ctx.need('Start', "Choose 'Autofill with Resume' or 'Apply Manually' yourself, then press Fill.");
      }
      if (doc.querySelector('[data-automation-id="applyFlowReviewPage"]')) {
        ctx.need('Review', 'Review page: check every answer and submit yourself.');
      } else if (doc.querySelector('[data-automation-id^="applyFlow"]')) {
        ctx.info('This page only', "Check it, click 'Save and Continue' yourself, then press Fill on the next page.");
      }
    },
    transform(q, f, v) {
      // Workday asks for the country code separately: the number field takes the national number.
      if (/phone number/i.test(q.label) && /^\+1\d{10}$/.test(v.replace(/[\s()-]/g, ''))) return v.replace(/[\s()-]/g, '').slice(2);
      return v;
    },
    async fill(ctx) {
      const work = sectionOf(ctx.doc, KINDS.work);
      const edu = sectionOf(ctx.doc, KINDS.edu);
      const exclude = [work, edu].filter(Boolean);
      await ctx.fillQuestions(() => collectWorkday(ctx.doc, exclude), { sort: countryFirst });
      if (work) await fillRepeating(ctx, work, KINDS.work);
      if (edu) await fillRepeating(ctx, edu, KINDS.edu);
    },
  });
})(globalThis);
