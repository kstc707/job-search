/*
 * DOM helpers shared by every adapter: finding controls (also inside open shadow roots),
 * reading a control's question label, setting values so React / Angular / Knockout forms
 * register them, choosing from custom dropdowns and type-ahead lists, attaching files,
 * highlighting, and the guard that refuses to click submit / next / apply buttons.
 *
 * Classic script injected into every frame (no imports, no top-level const: injecting it
 * twice must not throw).
 */
(function (root) {
  'use strict';

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /** querySelectorAll that also looks inside open shadow roots (SmartRecruiters, Oracle). */
  function deepQueryAll(scope, selector) {
    const out = [];
    const visit = (node) => {
      if (!node || !node.querySelectorAll) return;
      out.push(...node.querySelectorAll(selector));
      for (const el of node.querySelectorAll('*')) if (el.shadowRoot) visit(el.shadowRoot);
    };
    visit(scope);
    return out;
  }

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    if (!el.getClientRects().length) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none';
  }

  /** Radios, checkboxes and file inputs are often hidden behind styled labels. */
  function isShown(el) {
    if (isVisible(el)) return true;
    const t = (el.type || '').toLowerCase();
    if (t === 'radio' || t === 'checkbox' || t === 'file') {
      const host = el.closest('label') || labelElementFor(el) || el.parentElement;
      return !!host && (isVisible(host) || (host.parentElement && isVisible(host.parentElement)));
    }
    return false;
  }

  const CONTROL_SEL = 'input, select, textarea, button, [role="listbox"], [role="option"], option, script, style, svg';

  /** Text of `el` without the text of form controls inside it, split into block-level chunks. */
  function textChunks(el) {
    const chunks = [];
    let current = null;
    let currentBlock = null;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const parent = n.parentElement;
      if (!parent || parent.closest(CONTROL_SEL) && el.contains(parent.closest(CONTROL_SEL))) continue;
      if (parent.closest('[aria-hidden="true"]') && !/^\s*[*✱]\s*$/.test(n.nodeValue)) continue;
      const t = n.nodeValue.replace(/\s+/g, ' ').trim();
      if (!t) continue;
      let block = parent;
      while (block !== el && block.parentElement && /^inline/.test(getComputedStyle(block).display)) {
        block = block.parentElement;
      }
      if (block !== currentBlock) {
        current = { block, text: t };
        chunks.push(current);
        currentBlock = block;
      } else {
        current.text += ' ' + t;
      }
    }
    return chunks.map((c) => c.text);
  }

  function ownText(el) {
    return textChunks(el).join(' ').replace(/\s+/g, ' ').trim();
  }

  /** Strip required markers and punctuation around a label. */
  function cleanLabel(text) {
    return String(text || '')
      .replace(/\s+/g, ' ')
      .replace(/^\s*[*✱]\s*/, '')
      .replace(/\s*\((required|optional)\)\s*$/i, '')
      .replace(/\s*[*✱]+\s*$/, '')
      .replace(/\s+required\s*$/i, '')
      .replace(/\s*:\s*$/, '')
      .trim();
  }

  function markedRequired(text) {
    const t = String(text || '').trim();
    return /^[*✱]|[*✱]\s*$|\(required\)\s*$/i.test(t);
  }

  function byIdInRoot(el, id) {
    if (!id) return null;
    const rootNode = el.getRootNode ? el.getRootNode() : document;
    return (rootNode.getElementById ? rootNode.getElementById(id) : null) || document.getElementById(id);
  }

  function labelElementFor(el) {
    if (el.id) {
      const rootNode = el.getRootNode ? el.getRootNode() : document;
      const scope = rootNode.querySelectorAll ? rootNode : document;
      try {
        const l = scope.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        if (l) return l;
      } catch (e) { /* odd id */ }
    }
    return el.closest('label');
  }

  /**
   * The question a control asks, in the order a screen reader would use:
   * aria-labelledby, <label for>, wrapping <label>, aria-label, then the nearest text around it,
   * then placeholder / title / name. Returns {label, raw} (raw keeps "*" for required checks).
   */
  function labelFor(el, groupSize) {
    const lb = el.getAttribute('aria-labelledby');
    if (lb) {
      const t = lb.split(/\s+/).map((id) => byIdInRoot(el, id)).filter(Boolean).map(ownText).join(' ').trim();
      if (t) return { label: cleanLabel(t), raw: t };
    }
    const l = labelElementFor(el);
    if (l) {
      const t = ownText(l);
      if (t) return { label: cleanLabel(t), raw: t };
    }
    const aria = el.getAttribute('aria-label');
    if (aria && aria.trim()) return { label: cleanLabel(aria), raw: aria };
    const near = nearestText(el, groupSize || 1);
    if (near) return near;
    const ph = el.getAttribute('placeholder') || el.getAttribute('title') || '';
    if (ph.trim()) return { label: cleanLabel(ph), raw: ph };
    const nm = (el.name || el.id || '').replace(/[_\-\[\].]+/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').trim();
    return { label: nm, raw: nm };
  }

  const FIELD_SEL = 'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"]), select, textarea, button[aria-haspopup="listbox"]';

  /** Walk up from the control while the ancestor holds no other field; its first text chunk is the label. */
  function nearestText(el, groupSize) {
    let node = el.parentElement;
    for (let depth = 0; node && depth < 5; depth++, node = node.parentElement) {
      if (node.querySelectorAll(FIELD_SEL).length > groupSize) break;
      const chunks = textChunks(node);
      if (chunks.length) {
        let raw = chunks[0];
        if (chunks[1] && /^[*✱]$/.test(chunks[1])) raw += ' *';
        return { label: cleanLabel(raw), raw };
      }
    }
    // A label sitting just before the control's wrapper ("<div>City</div><div><input></div>").
    const prev = el.parentElement && el.parentElement.previousElementSibling;
    if (prev && !prev.querySelector(FIELD_SEL)) {
      const t = ownText(prev);
      if (t && t.length < 200) return { label: cleanLabel(t), raw: t };
    }
    return null;
  }

  const REQUIRED_MARK = '.required, .is-required, ._required, abbr[title="required" i], [data-required="true"], .field-required, .iCIMS_Required';

  function isRequired(el, raw, container) {
    if (el && (el.required || el.getAttribute('aria-required') === 'true')) return true;
    if (markedRequired(raw)) return true;
    if (container && container.querySelector && container.querySelector(REQUIRED_MARK)) return true;
    return false;
  }

  // ---------- events and value setting ----------

  function fire(el, type, Ctor, init) {
    const C = Ctor || Event;
    el.dispatchEvent(new C(type, Object.assign({ bubbles: true, cancelable: true, composed: true }, init || {})));
  }

  /**
   * Set a value the way a typing user would, so framework forms notice it:
   * the prototype's native setter (bypasses React's value tracker), then input / change / blur.
   */
  function setNativeValue(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
  }

  function setValue(el, value) {
    el.focus({ preventScroll: true });
    fire(el, 'focusin', FocusEvent);
    setNativeValue(el, value);
    fire(el, 'input', InputEvent, { inputType: 'insertText', data: String(value) });
    fire(el, 'change');
    blur(el);
    return el.value;
  }

  function blur(el) {
    fire(el, 'focusout', FocusEvent);
    if (el.blur) el.blur();
    el.dispatchEvent(new FocusEvent('blur', { bubbles: false, composed: true }));
  }

  function key(el, k, extra) {
    const code = k === 'Enter' ? 13 : k === 'Escape' ? 27 : k === 'ArrowDown' ? 40 : k === 'Tab' ? 9 : k.length === 1 ? k.toUpperCase().charCodeAt(0) : 0;
    const init = Object.assign({ key: k, code: k.length === 1 ? 'Key' + k.toUpperCase() : k, keyCode: code, which: code }, extra || {});
    fire(el, 'keydown', KeyboardEvent, init);
    if (k.length === 1) fire(el, 'keypress', KeyboardEvent, init);
    fire(el, 'keyup', KeyboardEvent, init);
  }

  /** Type character by character: type-ahead lists only search on keystrokes. */
  async function typeInto(el, text, opts) {
    const o = opts || {};
    el.focus({ preventScroll: true });
    fire(el, 'focusin', FocusEvent);
    setNativeValue(el, '');
    fire(el, 'input', InputEvent, { inputType: 'deleteContentBackward' });
    let typed = '';
    for (const ch of String(text)) {
      typed += ch;
      fire(el, 'keydown', KeyboardEvent, { key: ch });
      setNativeValue(el, typed);
      fire(el, 'input', InputEvent, { inputType: 'insertText', data: ch });
      fire(el, 'keyup', KeyboardEvent, { key: ch });
      await sleep(o.delay == null ? 12 : o.delay);
    }
    if (o.enter) key(el, 'Enter');
  }

  function selectNative(select, optionLabel) {
    const opts = [...select.options];
    const i = opts.findIndex((o) => o.text.trim() === optionLabel);
    if (i < 0) return `option '${optionLabel}' not found`;
    select.focus({ preventScroll: true });
    setNativeValue(select, opts[i].value);
    select.selectedIndex = i;
    fire(select, 'input');
    fire(select, 'change');
    blur(select);
    const got = select.options[select.selectedIndex] && select.options[select.selectedIndex].text.trim();
    return got === optionLabel ? null : `selected '${got}'`;
  }

  // ---------- the submit guard ----------

  const FORBIDDEN_TEXT = /\b(submit|next|apply|continue|review|send|finish|sign ?in|log ?in|sign ?up|register|create account|save and continue|save & continue|proceed)\b/i;
  const FORBIDDEN_ID = /submit|next|apply|continue|pagefooter|bottom-navigation|signin|createaccount|login|review/i;

  /** True for anything that would move the application forward: those clicks are the user's. */
  function isForbidden(el) {
    const b = el.closest('button, input[type="submit"], input[type="button"], input[type="image"], a[href], [role="button"], [role="link"]');
    if (!b) return false;
    if (b.matches('[aria-haspopup], [role="combobox"]') || b.closest('[role="listbox"]')) return false;
    if (b.matches('input[type="submit"], input[type="image"]')) return true;
    if (b.tagName === 'A') {
      const href = b.getAttribute('href') || '';
      if (href && !href.startsWith('#') && !/^javascript:/i.test(href)) return true;
    }
    const text = [b.innerText || b.value || '', b.getAttribute('aria-label') || '', b.getAttribute('title') || ''].join(' ');
    const ids = [b.id || '', b.getAttribute('data-automation-id') || '', b.getAttribute('name') || '', b.className && b.className.baseVal === undefined ? b.className : ''].join(' ');
    if (FORBIDDEN_TEXT.test(text) || FORBIDDEN_ID.test(ids)) return true;
    // A plain <button> inside a <form> submits it unless it says otherwise.
    if (b.tagName === 'BUTTON' && b.type === 'submit' && b.form && !/^(add|add another|yes|no|attach|upload|remove)$/i.test(text.trim())) return true;
    return false;
  }

  /** Click like a mouse would (pointer + mouse events, then click), never on a forbidden button. */
  function clickEl(el) {
    if (isForbidden(el)) throw new Error(`refused to click '${(el.innerText || el.value || '').trim().slice(0, 40)}' (submit/next/apply)`);
    if (el.scrollIntoView) el.scrollIntoView({ block: 'center', inline: 'nearest' });
    const r = el.getBoundingClientRect();
    const at = { clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, button: 0, view: window };
    const P = typeof PointerEvent === 'function' ? PointerEvent : MouseEvent;
    fire(el, 'pointerover', P, at);
    fire(el, 'mouseover', MouseEvent, at);
    fire(el, 'pointerdown', P, Object.assign({ pointerType: 'mouse', isPrimary: true }, at));
    fire(el, 'mousedown', MouseEvent, at);
    if (el.focus) el.focus({ preventScroll: true });
    fire(el, 'pointerup', P, Object.assign({ pointerType: 'mouse', isPrimary: true }, at));
    fire(el, 'mouseup', MouseEvent, at);
    el.click();
  }

  /**
   * While a fill runs, cancel every form submission in this frame. Belt and braces on top of
   * isForbidden(): even a button the page wires oddly cannot send the application.
   */
  let blocker = null;
  function blockSubmits(on) {
    if (on && !blocker) {
      blocker = (e) => { e.preventDefault(); e.stopImmediatePropagation(); };
      window.addEventListener('submit', blocker, true);
    } else if (!on && blocker) {
      window.removeEventListener('submit', blocker, true);
      blocker = null;
    }
  }

  function setChecked(box, want) {
    if (box.checked === want) return null;
    try {
      clickEl(box);
    } catch (e) { return e.message; }
    if (box.checked !== want) {
      // Custom-styled choices hide the real input: click its label instead.
      const l = labelElementFor(box);
      if (l) { try { clickEl(l); } catch (e) { /* ignore */ } }
    }
    return box.checked === want ? null : `did not stay ${want ? 'checked' : 'unchecked'}`;
  }

  // ---------- waiting, lists and type-aheads ----------

  async function waitFor(fn, timeout, interval) {
    const end = Date.now() + (timeout == null ? 3000 : timeout);
    for (;;) {
      const v = fn();
      if (v) return v;
      if (Date.now() > end) return null;
      await sleep(interval || 100);
    }
  }

  const OPTION_SEL = '[role="option"], [data-automation-id="promptOption"], .select__option, .oj-listbox-result-selectable, .dropdown-location, .autocomplete-suggestion, .pac-item';

  function optionText(el) {
    const t = el.getAttribute('data-automation-label') || el.innerText || el.textContent || '';
    return t.split('\n').map((s) => s.trim()).filter(Boolean)[0] || el.getAttribute('aria-label') || '';
  }

  /** Options currently shown for a dropdown: its aria-controls list if any, else any visible list. */
  function visibleOptions(trigger) {
    let scopes = [];
    for (const attr of ['aria-controls', 'aria-owns']) {
      const ids = (trigger.getAttribute(attr) || '').split(/\s+/).filter(Boolean);
      for (const id of ids) { const s = byIdInRoot(trigger, id); if (s) scopes.push(s); }
    }
    if (!scopes.length) scopes = [document];
    let els = [];
    for (const s of scopes) els.push(...deepQueryAll(s, OPTION_SEL));
    els = els.filter((e) => isVisible(e) && !e.closest('[aria-hidden="true"]') && e.getAttribute('aria-disabled') !== 'true');
    // Keep the innermost element when option markup is nested.
    els = els.filter((e) => !els.some((o) => o !== e && e.contains(o)));
    return els.map((el) => ({ el, text: optionText(el) })).filter((o) => o.text);
  }

  function closeList(trigger) {
    key(trigger, 'Escape');
    if (document.activeElement && document.activeElement !== trigger) key(document.activeElement, 'Escape');
  }

  /**
   * Choose from a custom dropdown or type-ahead.
   * candidates: answer wordings in priority order (answers.js pickOption semantics), or a single
   * "City, ST" with {location: true} (pickLocation). First opens the list without typing (so a
   * short list is matched like a native select), then types each wording for search boxes.
   */
  async function chooseFromList(trigger, candidates, opts) {
    const o = opts || {};
    const A = root.AutofillAnswers;
    const typable = trigger.matches('input:not([readonly]):not([type="checkbox"]):not([type="radio"]), textarea');
    let last = [];
    const pick = (texts) => {
      if (o.location) return A.pickLocation(texts, candidates[0]);
      const hit = A.pickOption(candidates, texts);
      return hit === null ? null : texts.indexOf(hit);
    };
    const attempt = async (typed) => {
      if (typed === null) {
        clickEl(trigger);
        if (typable) key(trigger, 'ArrowDown');
      } else {
        await typeInto(trigger, typed, { enter: o.enter });
      }
      let options = await waitFor(() => { const v = visibleOptions(trigger); return v.length ? v : null; }, typed === null ? 1200 : (o.timeout || 4000));
      if (!options) return null;
      await sleep(250); // let the list settle after the last keystroke
      options = visibleOptions(trigger);
      const texts = options.map((x) => x.text);
      last = texts;
      const i = pick(texts);
      if (i === null || i === undefined) return null;
      clickEl(options[i].el);
      await sleep(200);
      return texts[i];
    };
    const tries = [];
    if (!o.location && !o.searchOnly) tries.push(null);
    if (typable) {
      if (o.location) tries.push(String(candidates[0]).split(',')[0].trim());
      else for (const c of candidates) if (!tries.includes(String(c))) tries.push(String(c));
    }
    for (const t of tries) {
      const got = await attempt(t);
      if (got) return { picked: got };
      closeList(trigger);
      await sleep(120);
    }
    if (typable) { setNativeValue(trigger, ''); fire(trigger, 'input', InputEvent, { inputType: 'deleteContentBackward' }); blur(trigger); }
    return { error: last.length ? `no option matches ${JSON.stringify(candidates)}: ${JSON.stringify(last.slice(0, 8))}` : 'no options appeared' };
  }

  // ---------- files ----------

  function b64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function makeFile(file) {
    return new File([b64ToBytes(file.base64)], file.filename, { type: file.type || 'application/pdf', lastModified: Date.now() });
  }

  /** Put the file into an <input type=file> through a DataTransfer, as a drop would. */
  function attachFile(input, file) {
    const dt = new DataTransfer();
    dt.items.add(makeFile(file));
    input.files = dt.files;
    fire(input, 'input');
    fire(input, 'change');
    return input.files.length === 1 && input.files[0].name === file.filename ? null : 'the page did not keep the file';
  }

  /** For drop zones without a reachable input. */
  function dropFile(zone, file) {
    const dt = new DataTransfer();
    dt.items.add(makeFile(file));
    for (const t of ['dragenter', 'dragover', 'drop']) fire(zone, t, DragEvent, { dataTransfer: dt });
    return null;
  }

  // ---------- highlighting ----------

  const STYLES = {
    filled: '2px solid rgba(26, 127, 55, 0.45)',
    needs: '2px solid #cf222e',
  };

  function highlight(el, kind) {
    if (!el || !el.style) return;
    if (!el.hasAttribute('data-autofill-outline')) {
      el.setAttribute('data-autofill-outline', el.style.getPropertyValue('outline') || '');
    }
    el.style.setProperty('outline', STYLES[kind], 'important');
    el.style.setProperty('outline-offset', '2px', 'important');
    el.setAttribute('data-autofill', kind);
  }

  function clearHighlights() {
    for (const el of deepQueryAll(document, '[data-autofill]')) {
      const prev = el.getAttribute('data-autofill-outline') || '';
      if (prev) el.style.setProperty('outline', prev); else el.style.removeProperty('outline');
      el.style.removeProperty('outline-offset');
      el.removeAttribute('data-autofill');
      el.removeAttribute('data-autofill-outline');
    }
  }

  /** The element worth outlining for a control (the visible box, not a hidden input). */
  function visualOf(el) {
    if (!el) return null;
    if (isVisible(el) && !/^(radio|checkbox|file)$/.test(el.type || '')) return el;
    const group = el.type === 'radio' ? el.closest('fieldset, [role="radiogroup"]') : null;
    let n = group || el.closest('label, [data-automation-id^="formField-"]') || el.parentElement;
    for (let i = 0; n && i < 4 && !isVisible(n); i++) n = n.parentElement;
    return n || el;
  }

  root.AutofillDom = {
    sleep, deepQueryAll, isVisible, isShown, textChunks, ownText, cleanLabel, markedRequired,
    labelFor, labelElementFor, nearestText, isRequired, FIELD_SEL, REQUIRED_MARK,
    fire, setNativeValue, setValue, typeInto, key, blur, selectNative, setChecked,
    isForbidden, clickEl, blockSubmits, waitFor, visibleOptions, optionText, chooseFromList, closeList,
    attachFile, dropFile, highlight, clearHighlights, visualOf, byIdInRoot,
  };
})(globalThis);
