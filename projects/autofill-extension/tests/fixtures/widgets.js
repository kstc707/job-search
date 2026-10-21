/*
 * Small imitations of the widgets real application forms use, for the end-to-end tests.
 * They are not copies of any ATS's code; they reproduce the behaviour the filler must cope with:
 *  - reactTrack: React's value tracker (an own `value` property on the input). A plain
 *    `input.value = x` updates the tracker, so React ignores the next input event; only the
 *    prototype setter + an input event reaches the app's state (window.__state).
 *  - reactSelect: a react-select combobox (Greenhouse): opens on mousedown / ArrowDown,
 *    filters on typing, options are [role=option].select__option.
 *  - typeahead: a location look-up that only searches after keystrokes, with a delay.
 *  - wdDropdown: Workday's button[aria-haspopup=listbox] that opens a [role=listbox] popup.
 *  - wdPrompt: Workday's multiselect search prompt (click lists categories, Enter searches).
 * Guards: window.__submitted / window.__forbiddenClicks record any submit or next click.
 */
(function () {
  window.__state = {};
  window.__submitted = false;
  window.__forbiddenClicks = [];

  window.guardButtons = function () {
    document.addEventListener('submit', (e) => { window.__submitted = true; e.preventDefault(); });
    for (const b of document.querySelectorAll('[data-forbidden]')) {
      b.addEventListener('click', (e) => { window.__forbiddenClicks.push(b.textContent.trim()); e.preventDefault(); });
    }
  };

  window.reactTrack = function (input, key) {
    const proto = Object.getPrototypeOf(input);
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    let tracked = input.value;
    Object.defineProperty(input, 'value', {
      configurable: true,
      get() { return desc.get.call(this); },
      set(v) { tracked = String(v); desc.set.call(this, v); },
    });
    const onEvent = () => {
      const now = desc.get.call(input);
      if (now === tracked) return; // React: "value did not change", no onChange
      tracked = now;
      window.__state[key] = now;
    };
    input.addEventListener('input', onEvent);
    input.addEventListener('change', onEvent);
  };

  function show(el, on) { el.style.display = on ? '' : 'none'; }

  window.reactSelect = function (input, options, key) {
    const control = input.closest('.select__control');
    const single = control.querySelector('.select__single-value');
    const menu = document.createElement('div');
    menu.id = input.id + '-listbox';
    menu.setAttribute('role', 'listbox');
    menu.className = 'select__menu';
    show(menu, false);
    control.after(menu);
    input.setAttribute('aria-controls', menu.id);
    const render = () => {
      const f = input.value.toLowerCase();
      menu.replaceChildren(...options.filter((o) => o.toLowerCase().includes(f)).map((o) => {
        const d = document.createElement('div');
        d.className = 'select__option';
        d.setAttribute('role', 'option');
        d.textContent = o;
        d.addEventListener('click', () => {
          single.textContent = o;
          window.__state[key] = o;
          input.value = '';
          show(menu, false);
          input.setAttribute('aria-expanded', 'false');
        });
        return d;
      }));
    };
    const open = () => { render(); show(menu, true); input.setAttribute('aria-expanded', 'true'); };
    control.addEventListener('mousedown', open);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') open();
      if (e.key === 'Escape') show(menu, false);
    });
    input.addEventListener('input', open);
  };

  window.typeahead = function (input, places, key) {
    const list = document.createElement('ul');
    list.setAttribute('role', 'listbox');
    list.id = input.id + '-results';
    input.setAttribute('aria-controls', list.id);
    show(list, false);
    input.after(list);
    let timer = null;
    input.addEventListener('keydown', (e) => { if (e.key === 'Escape') show(list, false); });
    input.addEventListener('input', () => {
      clearTimeout(timer);
      show(list, false);
      const q = input.value.trim().toLowerCase();
      if (q.length < 3) return;
      timer = setTimeout(() => {
        list.replaceChildren(...places.filter((p) => p.toLowerCase().includes(q)).map((p) => {
          const li = document.createElement('li');
          li.setAttribute('role', 'option');
          li.textContent = p;
          li.addEventListener('click', () => {
            input.value = p;
            window.__state[key] = p;
            show(list, false);
          });
          return li;
        }));
        show(list, true);
      }, 300);
    });
  };

  window.wdDropdown = function (button, options, key, onPick) {
    let popup = null;
    const close = () => { if (popup) popup.remove(); popup = null; button.setAttribute('aria-expanded', 'false'); };
    button.addEventListener('click', (e) => {
      e.preventDefault();
      if (popup) { close(); return; }
      popup = document.createElement('div');
      popup.setAttribute('data-automation-id', 'selectListPopup');
      const ul = document.createElement('ul');
      ul.setAttribute('role', 'listbox');
      for (const o of options) {
        const li = document.createElement('li');
        li.setAttribute('role', 'option');
        const div = document.createElement('div');
        div.textContent = o;
        li.append(div);
        li.addEventListener('click', () => {
          button.textContent = o;
          button.value = o;
          window.__state[key] = o;
          close();
          if (onPick) onPick(o);
        });
        ul.append(li);
      }
      popup.append(ul);
      document.body.append(popup);
      button.setAttribute('aria-expanded', 'true');
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); }, true);
  };

  window.wdPrompt = function (input, top, search, key) {
    const container = input.closest('[data-automation-id="multiselectInputContainer"]');
    const pills = document.createElement('div');
    pills.className = 'pills';
    container.before(pills);
    let popup = null;
    const close = () => { if (popup) popup.remove(); popup = null; };
    const open = (items) => {
      close();
      if (!items.length) return;
      popup = document.createElement('div');
      popup.setAttribute('data-automation-id', 'activeListContainer');
      for (const o of items) {
        const d = document.createElement('div');
        d.setAttribute('data-automation-id', 'promptOption');
        d.setAttribute('data-automation-label', o);
        d.setAttribute('role', 'option');
        d.textContent = o;
        d.addEventListener('click', () => {
          const pill = document.createElement('div');
          pill.setAttribute('data-automation-id', 'selectedItem');
          pill.textContent = o;
          pills.replaceChildren(pill);
          window.__state[key] = o;
          input.value = '';
          close();
        });
        popup.append(d);
      }
      document.body.append(popup);
    };
    input.addEventListener('click', () => open(top));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); open(search(input.value)); }
      if (e.key === 'Escape') close();
    });
  };
})();
