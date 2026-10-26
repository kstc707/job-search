"""Fill a hosted Greenhouse application form in a real browser.

Locates inputs by the API field name (= DOM id), so labels never have to be parsed.
Text uses Playwright's fill (which fires the input/change events React forms need),
files use set_input_files, single-selects are type-ahead comboboxes, multi-selects
are checkboxes with id "{name}[]_{option value}".

Every filled value is read back from the page. Submitting is a separate, explicit flag.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .answers import Resolution
from .domform import fill_location
from .schema import form_url

CHROMIUM = os.environ.get("REA_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


@dataclass
class FillReport:
    filled: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # "label: reason"
    hidden: list[str] = field(default_factory=list)  # optional fields the form did not show
    captcha: bool = False
    screenshot: str = ""
    submitted: bool = False
    confirmation: str = ""
    code_requested: bool = False  # Greenhouse emailed a security code before accepting the submit


def _settle(page) -> None:
    """Wait until the form's scripts are running: a file attached before that is silently
    ignored. Some boards never go fully network-idle, so this wait is bounded."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass


def _css_id(name: str) -> str:
    if name.startswith("demographic_"):  # demographic questions render with the question id
        name = name[len("demographic_"):]
    return f'[id="{name}"]'


def _group(name: str) -> str:
    """Checkbox ids are "<name>[]_<value>"; some boards already end the name with "[]"."""
    return name[:-2] if name.endswith("[]") else name


def _on_page(page, f) -> bool:
    """Whether the form rendered this field (checkbox groups have one id per option)."""
    if page.locator(_css_id(f.name)).count():
        return True
    return f.type == "multi_value_multi_select" and bool(f.options) and \
        page.locator(_css_id(f"{_group(f.name)}[]_{f.options[0].value}")).count() > 0


def _pick(page, name: str, value: str) -> str | None:
    """Choose one option in a type-ahead select and check it is shown as chosen."""
    box = page.locator(_css_id(name))
    box.click()
    box.fill(value)
    option = page.get_by_role("option", name=value, exact=True)
    if option.count() == 0:
        option = page.locator('[role="option"]', has_text=value)
    option.first.click()
    # The chosen label is rendered next to the combobox input.
    container = box.locator("xpath=ancestor::div[contains(@class,'select__control') or contains(@class,'select-shell')][1]")
    shown = container.inner_text() if container.count() else ""
    return None if value in shown else f"selected value not shown (saw '{shown[:40]}')"


def _fill_one(page, r: Resolution) -> str | None:
    """Fill one field; return None on success or a reason string on failure."""
    f, label = r.field, r.question.label
    if f.type == "input_file":
        page.set_input_files(_css_id(f.name), r.value)
        name = Path(r.value).name
        page.wait_for_function("n => document.body.innerText.includes(n)", arg=name, timeout=15000)
        return None
    if f.name == "location":  # location look-up; it also sets the hidden latitude/longitude
        box = page.locator('[id="candidate-location"]')
        reason = fill_location(page, box, '[id^="react-select-candidate-location-option"]', r.value)
        if reason:
            return reason
        shown = box.locator("xpath=ancestor::div[contains(@class,'select__control')][1]").inner_text()
        return None if r.value.split(",")[0] in shown else f"location not shown (saw '{shown[:40]}')"
    if f.type in ("input_text", "textarea"):
        loc = page.locator(_css_id(f.name))
        loc.fill(r.value)
        got = loc.input_value()
        if f.name == "phone":  # the phone widget reformats; compare digits only
            same = re.sub(r"\D", "", got) == re.sub(r"\D", "", r.value)
        else:
            same = got.strip() == r.value.strip()
        return None if same else f"read back '{got[:40]}'"
    if f.type == "multi_value_single_select":
        return _pick(page, f.name, r.value)
    if f.type == "multi_value_multi_select" and f.name.startswith("demographic_"):
        # Multi-choice demographic questions are type-ahead boxes too, one pick per option.
        for value in r.value:
            reason = _pick(page, f.name, value)
            if reason:
                return reason
        return None
    if f.type == "multi_value_multi_select":
        values = {o.label: o.value for o in f.options}
        for lab in r.value:
            cb = page.locator(_css_id(f"{_group(f.name)}[]_{values[lab]}"))
            try:
                cb.check(timeout=5000)
            except Exception:  # styled checkbox: the real input is hidden, click its label
                cb.evaluate("e => (document.querySelector(`label[for='${e.id}']`) || e.closest('label') || e).click()")
            if not cb.is_checked():
                return f"checkbox '{lab}' did not stay checked"
        return None
    return f"unsupported field type {f.type} ({label})"


CONFIRMED = "text=/thank you|application (has been )?(received|submitted)/i"
CODE_PROMPT = re.compile(r"verification code was sent", re.I)


def wait_for_code(path: str, timeout: float, poll: float = 3.0) -> str:
    """The security code Greenhouse emails before it accepts a submission. The caller (an
    agent reading the inbox) writes it to `path`; return it, or "" when `timeout` passes."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        p = Path(path)
        if p.exists():
            code = re.sub(r"\s", "", p.read_text())
            if code:
                return code
        time.sleep(poll)
    return ""


def _enter_code(page, code: str) -> None:
    boxes = page.locator("input[id^='security-input']")
    if boxes.count() >= len(code):
        for i, ch in enumerate(code):
            boxes.nth(i).fill(ch)
        return
    # Fallback: focus the first one-character box after the prompt and type; the boxes advance.
    page.locator("input[maxlength='1']").first.click()
    page.keyboard.type(code, delay=80)


def fill_form(url: str, plan: list[Resolution], screenshot: str, *, submit: bool = False,
              headless: bool = True, code_file: str | None = None, code_wait: float = 600) -> FillReport:
    from playwright.sync_api import sync_playwright

    report = FillReport(screenshot=screenshot)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM, headless=headless)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(form_url(url), wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[id="first_name"]', timeout=30000)
        _settle(page)
        page.set_default_timeout(10000)  # one stuck field must not hold the run for long
        for r in plan:
            if r.status != "fill":
                continue
            if not r.question.required and not _on_page(page, r.field):
                # Conditional optional field (e.g. Race after a declined Hispanic/Latino answer).
                # Conditional optional field (e.g. Race after a declined Hispanic/Latino answer).
                report.hidden.append(r.question.label)
                continue
            try:
                reason = _fill_one(page, r)
            except Exception as e:  # one bad field must not abort the rest
                reason = f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"
            (report.failed.append(f"{r.question.label}: {reason}") if reason
             else report.filled.append(r.question.label))
        report.captcha = page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha']").count() > 0
        page.screenshot(path=screenshot, full_page=True)

        if submit:
            if report.failed:
                raise RuntimeError("refusing to submit: some fields failed to fill")
            if code_file:
                Path(code_file).unlink(missing_ok=True)  # never reuse a code from an earlier attempt
            page.get_by_role("button", name="Submit application").click()
            try:
                page.wait_for_selector(CONFIRMED, timeout=20000 if code_file else 45000)
                report.submitted = True
                report.confirmation = page.locator("body").inner_text()[:300]
            except Exception:
                report.confirmation = "no confirmation page (captcha challenge or validation error?)"
                if code_file and page.get_by_text(CODE_PROMPT).count():
                    report.code_requested = True
                    print(f"WAITING FOR SECURITY CODE: write the emailed code to {code_file}", flush=True)
                    code = wait_for_code(code_file, code_wait)
                    if not code:
                        report.confirmation = f"security code not supplied within {code_wait:.0f}s"
                    else:
                        _enter_code(page, code)
                        page.get_by_role("button", name="Submit application").click()
                        try:
                            page.wait_for_selector(CONFIRMED, timeout=45000)
                            report.submitted = True
                            report.confirmation = page.locator("body").inner_text()[:300]
                        except Exception:
                            report.confirmation = "security code entered, but no confirmation page"
            page.screenshot(path=screenshot.replace(".png", "-after-submit.png"), full_page=True)
        browser.close()
    return report
