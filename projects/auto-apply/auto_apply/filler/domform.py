"""Read and fill application forms rendered on the page (Lever, Ashby).

Greenhouse publishes its questions through an API (schema.py). Lever and Ashby do not, so the
questions are read from the live form. Each system gets a small profile describing where a
question's label lives and how "required" is marked; everything else is shared.

Every Field.name here is a CSS selector for the input, so filling never re-parses labels.
Option values are selectors too (one per checkbox/radio) or the option label (native selects).
"""

from __future__ import annotations

from pathlib import Path

from .schema import Field, Option, Question

# How each system marks up a question. Selectors observed on live forms (2026-10-15).
PROFILES = {
    "lever": {
        "container": "li.application-question, div.application-question",
        "label": ".application-label",
        "required": ".required",
    },
    "ashby": {
        "container": ".ashby-application-form-field-entry",
        "label": "label.ashby-application-form-question-title",
        "required_label_class": "_required",
    },
}

_READ_JS = """
(root, prof) => {
  const out = [];
  const css = s => s.replace(/(["\\\\])/g, '\\\\$1');
  for (const box of root.querySelectorAll(prof.container)) {
    const labEl = box.querySelector(prof.label);
    let label = (labEl ? labEl.innerText : box.innerText).split('\\n')[0].replace(/[✱*]\\s*$/, '').trim();
    if (!label) continue;
    let required = false;
    if (prof.required && box.querySelector(prof.required)) required = true;
    if (prof.required_label_class && labEl && labEl.className.includes(prof.required_label_class)) required = true;
    const inputs = [...box.querySelectorAll('input, textarea, select')].filter(i => i.type !== 'hidden');
    if (inputs.some(i => i.required)) required = true;
    const fields = [];
    const byName = {};
    const path = box.getAttribute('data-field-path');
    for (const i of inputs) {
      const key = i.name || i.id;
      if ((i.type === 'checkbox' || i.type === 'radio') && key) { (byName[key] = byName[key] || []).push(i); continue; }
      // Some inputs carry neither id nor name: locate them inside their question instead.
      const sel = i.id ? `[id="${css(i.id)}"]` : i.name ? `[name="${css(i.name)}"]`
          : path ? `[data-field-path="${css(path)}"] ${i.tagName.toLowerCase()}` : null;
      if (!sel) continue;
      if (i.type === 'file') fields.push({name: sel, type: 'input_file', options: []});
      else if (i.tagName === 'TEXTAREA') fields.push({name: sel, type: 'textarea', options: []});
      else if (i.tagName === 'SELECT') fields.push({name: sel, type: 'native_select',
          options: [...i.options].filter(o => o.value !== '').map(o => ({label: o.text.trim(), value: o.text.trim()}))});
      else if (i.getAttribute('role') === 'combobox' || box.querySelector('input[name="selectedLocation"]'))
          fields.push({name: sel, type: 'autocomplete', options: []});
      else fields.push({name: sel, type: 'input_text', options: []});
    }
    const extra = [];
    for (const [key, group] of Object.entries(byName)) {
      const opts = group.map(i => {
        const l = i.closest('label') || box.querySelector(`label[for="${css(i.id)}"]`);
        const text = (l ? l.innerText : i.value).trim();
        const sel = i.id ? `[id="${css(i.id)}"]` : `input[name="${css(key)}"][value="${css(i.value)}"]`;
        return {label: text, value: sel};
      });
      const f = {name: `[name="${css(key)}"]`, type: group[0].type === 'radio' ? 'radio' : 'multi_value_multi_select', options: opts};
      // A choice group sitting next to a typed answer is a separate question
      // (Ashby: Phone + "consent to text messages"); name it after the group.
      if (fields.length) extra.push({label: `${label} — ${key}`, required, fields: [f]});
      else fields.push(f);
    }
    // Ashby yes/no questions: two buttons over a hidden checkbox.
    const yes = [...box.querySelectorAll('button')].filter(b => /^(yes|no)$/i.test(b.innerText.trim()));
    if (yes.length === 2) {
      const yp = path || (box.querySelector('[data-field-path]') || {}).getAttribute?.('data-field-path') || label;
      fields.splice(0, fields.length, {name: `[data-field-path="${css(yp)}"]`, type: 'yesno',
        options: [{label: 'Yes', value: 'Yes'}, {label: 'No', value: 'No'}]});
    }
    if (fields.length) out.push({label, required, fields});
    out.push(...extra);
  }
  return out;
}
"""


def detect_ats(url: str) -> str | None:
    host = url.split("/")[2].lower() if "://" in url else ""
    if host.endswith("lever.co"):
        return "lever"
    if host.endswith("ashbyhq.com"):
        return "ashby"
    if host.endswith("greenhouse.io"):
        return "greenhouse"
    return None


def apply_url(url: str, ats: str) -> str:
    """The page that holds the form (Lever: /apply, Ashby: /application)."""
    u = url.split("?")[0].rstrip("/")
    if ats == "lever" and not u.endswith("/apply"):
        return u + "/apply"
    if ats == "ashby" and not u.endswith("/application"):
        return u + "/application"
    return u


def read_form(page, ats: str) -> list[Question]:
    raw = page.evaluate(f"(prof) => ({_READ_JS})(document, prof)", PROFILES[ats])
    return questions_from_raw(raw)


def questions_from_raw(raw: list[dict]) -> list[Question]:
    return [
        Question(q["label"], bool(q["required"]),
                 [Field(f["name"], f["type"], [Option(o["label"], o["value"]) for o in f["options"]])
                  for f in q["fields"]], "page")
        for q in raw
    ]


SUBMIT = {
    "lever": "#btn-submit",
    "ashby": "button.ashby-application-form-submit-button",
}
CAPTCHA = "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='turnstile']"


def open_and_plan(url: str, ats: str, bank, *, headless: bool = True):
    """Start a browser session on the form, read it and plan every answer.

    Returns (session, title, plan); call session.fill(...) next, then session.close().
    One session per job, so the page that was read is the page that gets filled.
    """
    return _Session(url, ats, bank, headless)


class _Session:
    def __init__(self, url, ats, bank, headless):
        from playwright.sync_api import sync_playwright

        from .greenhouse import CHROMIUM

        self.ats = ats
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(executable_path=CHROMIUM, headless=headless)
        self.page = self._browser.new_page(viewport={"width": 1280, "height": 900})
        self.page.goto(apply_url(url, ats), wait_until="networkidle", timeout=60000)
        self.page.wait_for_selector(PROFILES[ats]["container"], timeout=30000)
        self.page.set_default_timeout(10000)  # one stuck field must not hold the run for long
        self.title = self.page.title()
        self.questions = read_form(self.page, ats)
        self.plan = bank.plan(self.questions)

    def fill(self, screenshot: str, *, submit: bool = False):
        from .greenhouse import FillReport

        report = FillReport(screenshot=screenshot)
        for r in self.plan:
            if r.status != "fill":
                continue
            if not r.question.required and not _visible(self.page, r.field):
                # Optional field the form keeps hidden (e.g. the disability form's signature).
                report.hidden.append(r.question.label)
                continue
            try:
                reason = fill_field(self.page, r)
            except Exception as e:  # one bad field must not abort the rest
                reason = f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"
            (report.failed.append(f"{r.question.label}: {reason}") if reason
             else report.filled.append(r.question.label))
        report.captcha = self.page.locator(CAPTCHA).count() > 0
        self.page.screenshot(path=screenshot, full_page=True)
        if submit:
            if report.failed:
                raise RuntimeError("refusing to submit: some fields failed to fill")
            self.page.locator(SUBMIT[self.ats]).first.click()
            try:
                self.page.wait_for_selector(
                    "text=/thank you|application (has been )?(received|submitted)|successfully submitted/i",
                    timeout=45000)
                report.submitted = True
                report.confirmation = self.page.locator("body").inner_text()[:300]
            except Exception:
                report.confirmation = "no confirmation page (captcha challenge or validation error?)"
            self.page.screenshot(path=screenshot.replace(".png", "-after-submit.png"), full_page=True)
        return report

    def close(self):
        self._browser.close()
        self._pw.stop()


def _visible(page, f) -> bool:
    sel = f.options[0].value if f.type in ("radio", "multi_value_multi_select") and f.options else f.name
    loc = page.locator(sel).first
    if f.type in ("radio", "multi_value_multi_select", "input_file"):
        # Real inputs are often hidden behind styled labels; judge by the label/container.
        return loc.count() > 0 and loc.evaluate("e => !!(e.closest('label, li, div') || e).offsetParent")
    return loc.count() > 0 and loc.is_visible()


def fill_field(page, r) -> str | None:
    """Fill one page-read field; return None on success or why it failed."""
    f, sel = r.field, r.field.name
    loc = page.locator(sel).first
    if f.type == "input_file":
        loc.set_input_files(r.value)
        # Lever/Ashby parse the resume and may autofill fields from it: wait until the upload
        # shows as done (Lever's "Success!" marker, or the file name on the page) and no
        # "analyzing" spinner is left, so parsing cannot overwrite answers typed afterwards.
        try:
            page.wait_for_function(
                """name => {
                  const t = document.body.innerText.toLowerCase();
                  const ok = [...document.querySelectorAll('.resume-upload-success')].some(e => e.offsetParent)
                          || t.includes(name.toLowerCase());
                  return ok && !/analy[sz]ing (your )?resume/.test(t);
                }""", arg=Path(r.value).name, timeout=30000)
        except Exception:
            return "resume upload did not finish in 30s"
        return None
    if f.type in ("input_text", "textarea"):
        loc.fill(r.value)
        got = loc.input_value()
        same = (got.strip() == r.value.strip()) or (
            "phone" in r.question.label.lower() and _digits(got) == _digits(r.value))
        return None if same else f"read back '{got[:40]}'"
    if f.type == "native_select":
        loc.select_option(label=r.value)
        got = loc.evaluate("e => e.options[e.selectedIndex]?.text.trim()")
        return None if got == r.value else f"selected '{got}'"
    if f.type in ("radio", "multi_value_multi_select"):
        values = {o.label: o.value for o in f.options}
        for lab in (r.value if isinstance(r.value, list) else [r.value]):
            box = page.locator(values[lab]).first
            try:
                box.check(force=True)
            except Exception:
                # Custom-styled choices hide the real input: click its label instead.
                box.evaluate("e => (e.closest('label') || document.querySelector(`label[for='${e.id}']`) || e).click()")
            if not box.is_checked():
                return f"'{lab}' did not stay checked"
        return None
    if f.type == "yesno":
        btn = page.locator(sel).first.get_by_role("button", name=r.value, exact=True)
        btn.click()
        # Ashby marks the chosen button with an "_active" class.
        active = btn.evaluate("b => /active|selected/i.test(b.className) || b.getAttribute('aria-pressed') === 'true'")
        return None if active else f"'{r.value}' button did not stay selected"
    if f.type == "autocomplete":
        return fill_location(page, loc, '[role="option"], .dropdown-location', r.value)
    return f"unsupported field type {f.type}"


US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


def pick_location(texts: list[str], value: str) -> int | None:
    """Index of the suggestion that is the place in `value` ("Memphis, TN"), or None.

    Suggestions word states differently ("Memphis, TN, USA", "Memphis, Tennessee, United
    States"), so match the city at the start and the state by code or full name. Never
    "West Memphis" for "Memphis".
    """
    city, _, rest = (x.strip() for x in value.partition(","))
    code = rest.split(",")[0].strip().upper()
    states = {code, US_STATES.get(code, code).upper()} if code else set()
    for i, t in enumerate(texts):
        parts = [x.strip() for x in t.split(",")]
        if _norm_words(parts[0]) != _norm_words(city):
            continue
        if not states or any(x.upper() in states for x in parts[1:]):
            return i
    return None


def fill_location(page, box, option_selector: str, value: str) -> str | None:
    """Type the city into a location look-up and click the matching suggestion."""
    city = value.split(",")[0].strip()
    box.click()
    box.fill("")
    box.press_sequentially(city, delay=60)  # look-ups only search on real keystrokes
    options = page.locator(option_selector)
    try:
        options.first.wait_for(timeout=8000)
    except Exception:
        return "no suggestion appeared for the typed location"
    page.wait_for_timeout(400)  # let the list settle after the last keystroke
    texts = options.all_inner_texts()
    i = pick_location(texts, value)
    if i is None:
        return f"no suggestion is '{value}': {texts[:4]}"
    options.nth(i).click()
    hidden = page.locator('input[name="selectedLocation"]')  # Lever records the pick here
    if hidden.count() and not hidden.first.input_value():
        return "suggestion clicked but the form did not record the location"
    return None


def _norm_words(s: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s.lower()).split())


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())
