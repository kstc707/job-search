/*
 * Reading questions from the page and filling one resolved answer.
 *
 * A question is {label, required, fields: [field]}; a field is
 * {type, name, el, options: [{label, el}] | null, location?, enter?} with the same `type`
 * names as the cloud filler (input_text, textarea, input_file, native_select, radio,
 * multi_value_multi_select, yesno, autocomplete) plus combobox (custom dropdown or type-ahead
 * whose options appear only when opened), checkbox (one box) and date (Workday month/year).
 *
 * Two collectors:
 *  - collectContainers: one question per container element (Lever, Ashby, Workday, Oracle);
 *    a port of the page reader in auto_apply/filler/domform.py.
 *  - collectGeneric: one question per control or choice group, label found from
 *    label[for] / aria-labelledby / aria-label / nearest text / placeholder (everything else).
 */
(function (root) {
  'use strict';
  const D = root.AutofillDom;

  const SKIP_AREAS = 'nav, header, footer, [role="search"], [role="navigation"], [aria-hidden="true"], [data-autofill-ignore]';
  const LOCATION_LABEL = /\blocation\b|^(current )?city\b|where (are you|do you) (located|live|based)/i;

  // ---------- adapter registry (idempotent: scripts may be injected more than once) ----------
  const registry = root.AutofillAdapters || { byId: {} };
  registry.register = function (adapter) { registry.byId[adapter.id] = adapter; };
  registry.list = function () {
    return Object.values(registry.byId).sort((a, b) => (a.order || 50) - (b.order || 50));
  };
  /** Hostname first (the frame's own host: iCIMS forms live in an icims.com iframe), then DOM. */
  registry.detect = function (loc, doc) {
    const host = (loc.hostname || '').toLowerCase();
    const all = registry.list();
    return all.find((a) => a.host && a.host.test(host) && (!a.path || a.path.test(loc.pathname)))
      || all.find((a) => a.sniff && a.sniff(doc))
      || registry.byId.generic;
  };
  root.AutofillAdapters = registry;

  // ---------- classifying controls ----------

  function nameOf(el) {
    return el.id || el.getAttribute('name') || el.getAttribute('data-automation-id') || '';
  }

  function isComboInput(el) {
    return el.getAttribute('role') === 'combobox' || /^(list|both)$/.test(el.getAttribute('aria-autocomplete') || '')
      || el.getAttribute('aria-haspopup') === 'listbox' || el.getAttribute('data-uxi-widget-type') === 'selectinput';
  }

  function selectOptions(sel) {
    // As the cloud filler: options with an empty value are placeholders ("Select...").
    return [...sel.options].filter((o) => o.value !== '').map((o) => ({ label: o.text.trim(), el: o }));
  }

  function optionLabel(box) {
    const l = D.labelElementFor(box);
    let t = l ? D.ownText(l) : '';
    if (!t) t = box.getAttribute('aria-label') || '';
    if (!t && box.nextSibling) t = (box.nextSibling.textContent || '').trim();
    return D.cleanLabel(t || box.value || '');
  }

  /** One field for a single (non-choice) control. */
  function singleField(el, label) {
    const tag = el.tagName;
    const type = (el.getAttribute('type') || '').toLowerCase();
    const base = { name: nameOf(el), el, options: [] };
    if (tag === 'SELECT') return Object.assign(base, { type: 'native_select', options: selectOptions(el) });
    if (tag === 'TEXTAREA') return Object.assign(base, { type: 'textarea' });
    if (type === 'file') return Object.assign(base, { type: 'input_file' });
    if (tag === 'BUTTON' || (tag !== 'INPUT' && el.getAttribute('role') === 'combobox')) {
      return Object.assign(base, { type: 'combobox', options: null });
    }
    if (isComboInput(el)) {
      if (LOCATION_LABEL.test(label || '')) return Object.assign(base, { type: 'autocomplete', location: true });
      return Object.assign(base, { type: 'combobox', options: null, enter: el.getAttribute('data-uxi-widget-type') === 'selectinput' });
    }
    return Object.assign(base, { type: 'input_text' });
  }

  function groupField(members) {
    const type = members[0].type === 'radio' ? 'radio' : 'multi_value_multi_select';
    return {
      type, name: members[0].name || nameOf(members[0]), el: members[0], members,
      options: members.map((m) => ({ label: optionLabel(m), el: m })),
    };
  }

  function commonAncestor(els) {
    let a = els[0].parentElement;
    while (a && !els.every((e) => a.contains(e))) a = a.parentElement;
    return a;
  }

  /** The question above a radio/checkbox group (legend, role=radiogroup label, or nearby text). */
  function groupLabel(members) {
    const first = members[0];
    const fs = first.closest('fieldset');
    if (fs && members.every((m) => fs.contains(m))) {
      const lg = fs.querySelector('legend');
      if (lg && D.ownText(lg)) { const raw = D.ownText(lg); return { label: D.cleanLabel(raw), raw, box: fs }; }
    }
    const rg = first.closest('[role="radiogroup"], [role="group"]');
    if (rg && members.every((m) => rg.contains(m))) {
      const lb = rg.getAttribute('aria-labelledby');
      const t = lb ? lb.split(/\s+/).map((id) => D.byIdInRoot(rg, id)).filter(Boolean).map(D.ownText).join(' ') : rg.getAttribute('aria-label');
      if (t && t.trim()) return { label: D.cleanLabel(t), raw: t, box: rg };
    }
    const optionTexts = new Set(members.map(optionLabel));
    let anc = members.length > 1 ? commonAncestor(members) : first.parentElement;
    for (let depth = 0; anc && depth < 5; depth++, anc = anc.parentElement) {
      const fields = anc.querySelectorAll(D.FIELD_SEL);
      if ([...fields].some((f) => !members.includes(f))) break;
      const chunks = D.textChunks(anc).filter((c) => !optionTexts.has(D.cleanLabel(c)) && !/^[*✱]$/.test(c));
      if (chunks.length) {
        const raw = chunks[0] + (D.textChunks(anc).some((c) => /^[*✱]$/.test(c)) ? ' *' : '');
        return { label: D.cleanLabel(raw), raw, box: anc };
      }
    }
    return null;
  }

  function usable(el, opts) {
    if (el.disabled) return false;
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (type === 'search') return false;
    if (el.tagName === 'INPUT' && el.readOnly && !isComboInput(el)) return false;
    if (el.closest(SKIP_AREAS)) return false;
    if (/honeypot|^hp_|bot.?trap/i.test(el.name || el.id || '')) return false;
    if (opts.exclude && opts.exclude.some((x) => x && x.contains(el))) return false;
    if (type === 'file') return true;
    return D.isShown(el);
  }

  /** One question per control or choice group, in page order. */
  function collectGeneric(scope, opts) {
    const o = opts || {};
    const controls = D.deepQueryAll(scope || document, D.FIELD_SEL + ', [role="combobox"]:not(input)')
      .filter((el) => !(el.matches('[role="combobox"]:not(input)') && el.querySelector('input')))
      .filter((el) => usable(el, o));
    const groups = new Map();
    const order = [];
    const holderIds = new Map();
    const hid = (h) => { if (!holderIds.has(h)) holderIds.set(h, holderIds.size); return holderIds.get(h); };
    for (const el of controls) {
      const type = (el.getAttribute('type') || '').toLowerCase();
      if (type === 'radio' || type === 'checkbox') {
        const holder = el.closest('fieldset, [role="radiogroup"], [role="group"]');
        const k = `${type}:${el.name || (holder ? 'g' + hid(holder) : 'x' + order.length)}`;
        if (!groups.has(k)) { groups.set(k, []); order.push({ group: k }); }
        groups.get(k).push(el);
      } else {
        order.push({ el });
      }
    }
    // Checkboxes without a name that share a fieldset/group belong together.
    const questions = [];
    for (const item of order) {
      if (item.el) {
        const el = item.el;
        const { label, raw } = D.labelFor(el, 1);
        if (!label) continue;
        const container = el.closest('.field, .form-group, .form-field, [class*="field-wrapper"], [class*="question"]') || el.parentElement;
        questions.push({ label, required: D.isRequired(el, raw, null) || (container && !!container.querySelector(':scope > .required, :scope > label .required, :scope > label abbr')), fields: [singleField(el, label)], el });
        continue;
      }
      const members = groups.get(item.group);
      if (members.length === 1 && members[0].type === 'checkbox') {
        const box = members[0];
        const own = optionLabel(box);
        const gl = groupLabel(members);
        const label = gl ? gl.label : own;
        const raw = gl ? gl.raw : (D.labelElementFor(box) ? D.ownText(D.labelElementFor(box)) : own);
        if (!label) continue;
        questions.push({ label, required: D.isRequired(box, raw, null), fields: [{ type: 'checkbox', name: nameOf(box), el: box, options: [{ label: own, el: box }] }], el: box });
        continue;
      }
      const gl = groupLabel(members) || { label: D.cleanLabel(members[0].name || ''), raw: '' };
      if (!gl.label) continue;
      const required = members.some((m) => m.required || m.getAttribute('aria-required') === 'true')
        || D.markedRequired(gl.raw) || (gl.box && gl.box.getAttribute && gl.box.getAttribute('aria-required') === 'true');
      questions.push({ label: gl.label, required, fields: [groupField(members)], el: members[0] });
    }
    return questions;
  }

  /**
   * One question per container: a port of domform.py's _READ_JS for Lever / Ashby, reused by
   * Oracle. prof = {container, label, required?, requiredLabelClass?}.
   */
  function collectContainers(scope, prof, opts) {
    const o = opts || {};
    const out = [];
    for (const box of D.deepQueryAll(scope || document, prof.container)) {
      if (o.exclude && o.exclude.some((x) => x && x.contains(box))) continue;
      if (!D.isVisible(box)) continue;
      const labEl = box.querySelector(prof.label);
      const rawText = (labEl ? labEl.innerText : box.innerText) || '';
      const label = rawText.split('\n')[0].replace(/[✱*]\s*$/, '').trim();
      if (!label) continue;
      let required = !!(prof.required && box.querySelector(prof.required));
      if (prof.requiredLabelClass && labEl && String(labEl.className).includes(prof.requiredLabelClass)) required = true;
      if (/[✱*]\s*$/.test(rawText.split('\n')[0])) required = true;
      const inputs = [...box.querySelectorAll('input, textarea, select, button[aria-haspopup="listbox"]')]
        .filter((i) => i.type !== 'hidden' && !(i.tagName === 'BUTTON' && i.getAttribute('aria-haspopup') !== 'listbox'));
      if (inputs.some((i) => i.required || i.getAttribute('aria-required') === 'true')) required = true;
      const fields = [];
      const byName = new Map();
      for (const i of inputs) {
        const k = i.name || i.id;
        if ((i.type === 'checkbox' || i.type === 'radio') && k) {
          if (!byName.has(k)) byName.set(k, []);
          byName.get(k).push(i);
          continue;
        }
        if (i.tagName === 'INPUT' && i.readOnly && !isComboInput(i)) continue;
        const f = singleField(i, label);
        if (box.querySelector('input[name="selectedLocation"]') && f.type === 'input_text') {
          Object.assign(f, { type: 'autocomplete', location: true });
        }
        fields.push(f);
      }
      const extra = [];
      for (const [k, group] of byName) {
        const f = group.length === 1 && group[0].type === 'checkbox'
          ? { type: 'checkbox', name: k, el: group[0], options: [{ label: optionLabel(group[0]), el: group[0] }] }
          : groupField(group);
        // A choice group next to a typed answer is a separate question (Ashby: Phone + SMS consent).
        if (fields.length) extra.push({ label: `${label} — ${k}`, required, fields: [f], el: group[0], box });
        else fields.push(f);
      }
      // Ashby / Oracle yes-no questions: two buttons over a hidden input.
      const yn = [...box.querySelectorAll('button')].filter((b) => /^(yes|no)$/i.test((b.innerText || '').trim()));
      if (yn.length === 2) {
        fields.splice(0, fields.length, {
          type: 'yesno', name: label, el: yn[0],
          options: yn.map((b) => ({ label: (b.innerText || '').trim().replace(/^./, (c) => c.toUpperCase()), el: b })),
        });
      }
      if (fields.length) out.push({ label, required, fields, el: fields[0].el, box });
      out.push(...extra);
    }
    return out;
  }

  // ---------- filling one field ----------

  const digits = (s) => String(s).replace(/\D+/g, '');

  /** Read back what a field shows now, to verify a fill. */
  function shownText(el) {
    const box = el.closest('[data-automation-id^="formField-"], .select__control, .select-shell, .application-question, .ashby-application-form-field-entry, .input-row, .form-group, .field') || el.parentElement || el;
    return (box.innerText || '') + ' ' + (el.value || '') + ' ' + (el.innerText || '');
  }

  function alreadyAttached(input, filename) {
    let n = input.parentElement;
    for (let i = 0; n && i < 4; i++, n = n.parentElement) {
      if ((n.innerText || '').includes(filename)) return true;
    }
    return false;
  }

  /**
   * Fill `field` with `value` (already resolved by the answer engine). Returns null on success
   * or the reason it failed. Never clicks submit/next/apply (D.clickEl refuses).
   */
  async function fillField(q, f, value, adapter) {
    const el = f.el;
    f.shown = undefined; // what the page ended up showing, for the report
    switch (f.type) {
      case 'input_file': {
        if (alreadyAttached(el, value.filename)) return null;
        const err = D.attachFile(el, value);
        await D.sleep(300);
        return err;
      }
      case 'input_text':
      case 'textarea': {
        let v = String(value);
        if (adapter && adapter.transform) v = adapter.transform(q, f, v);
        if (el.tagName === 'INPUT' && el.type === 'date') {
          const d = root.AutofillAnswers.parseDate(v);
          if (!d.year) return `'${v}' is not a date`;
          v = `${d.year}-${String(d.month || 1).padStart(2, '0')}-01`;
        }
        D.setValue(el, v);
        f.shown = v;
        await D.sleep(30);
        const got = el.value || '';
        const same = got.trim() === v.trim() || (/phone|mobile/i.test(q.label) && digits(got) && digits(v).endsWith(digits(got)));
        return same ? null : `read back '${got.slice(0, 40)}'`;
      }
      case 'native_select':
        return D.selectNative(el, value);
      case 'radio':
      case 'multi_value_multi_select': {
        for (const lab of Array.isArray(value) ? value : [value]) {
          const opt = f.options.find((x) => x.label === lab);
          if (!opt) return `option '${lab}' not found`;
          const err = D.setChecked(opt.el, true);
          if (err) return `'${lab}' ${err}`;
        }
        return null;
      }
      case 'checkbox':
        return D.setChecked(el, !!value);
      case 'yesno': {
        const opt = f.options.find((x) => x.label === value);
        if (!opt) return `no '${value}' button`;
        D.clickEl(opt.el);
        await D.sleep(80);
        const b = opt.el;
        const active = /active|selected/i.test(String(b.className)) || b.getAttribute('aria-pressed') === 'true' || b.getAttribute('aria-checked') === 'true';
        return active ? null : `'${value}' button did not stay selected`;
      }
      case 'combobox': {
        const candidates = Array.isArray(value) ? value : [value];
        const out = await D.chooseFromList(el, candidates, { enter: f.enter });
        if (out.error) return out.error;
        f.shown = out.picked;
        return shownText(el).includes(out.picked) ? null : `picked '${out.picked}' but the form does not show it`;
      }
      case 'autocomplete': {
        const out = await D.chooseFromList(el, [String(value)], { location: true });
        if (out.error) return out.error;
        f.shown = out.picked;
        const hidden = el.closest('form, body').querySelector('input[name="selectedLocation"]');
        if (hidden && !hidden.value) return 'suggestion clicked but the form did not record the location';
        return null;
      }
      case 'date':
        return fillDate(f, value);
      default:
        return `unsupported field type ${f.type}`;
    }
  }

  /** Workday-style split dates: month / day / year inputs inside one field. */
  async function fillDate(f, value) {
    const d = typeof value === 'object' ? value : root.AutofillAnswers.parseDate(value);
    const parts = [['month', f.parts.month, d.month], ['year', f.parts.year, d.year]];
    for (const [name, input, v] of parts) {
      if (!input) continue;
      if (v == null) return `no ${name} in '${JSON.stringify(value)}'`;
      const text = name === 'month' ? String(v).padStart(2, '0') : String(v);
      await D.typeInto(input, text, { delay: 5 });
      D.fire(input, 'change');
      D.blur(input);
      await D.sleep(30);
      if (digits(input.value) !== digits(text) && Number(digits(input.value)) !== Number(text)) return `${name} reads back '${input.value}'`;
    }
    return null;
  }

  /** Does the field already hold a value (prefilled by the site, or by the user)? */
  function hasValue(f) {
    const el = f.el;
    switch (f.type) {
      case 'input_text':
      case 'textarea':
      case 'autocomplete':
        return !!String(el.value || '').trim();
      case 'native_select': {
        const o = el.options[el.selectedIndex];
        return !!o && o.value !== '';
      }
      case 'radio':
      case 'multi_value_multi_select':
        return f.options.some((o) => o.el.checked);
      case 'combobox': {
        if (el.tagName === 'BUTTON') return !/^(select( one)?|choose.*|please select|--.*|)$/i.test((el.innerText || '').trim());
        const box = el.closest('[data-automation-id^="formField-"], .select__control, .field, .form-group') || el.parentElement;
        return !!(box && box.querySelector('[data-automation-id="selectedItem"], .select__single-value:not(:empty)')) || !!String(el.value || '').trim();
      }
      case 'input_file':
        return !!(el.files && el.files.length);
      default:
        return false;
    }
  }

  root.AutofillCollect = {
    hasValue,
    collectGeneric, collectContainers, singleField, groupField, groupLabel, optionLabel,
    fillField, nameOf, isComboInput, LOCATION_LABEL, usable,
  };
})(globalThis);
