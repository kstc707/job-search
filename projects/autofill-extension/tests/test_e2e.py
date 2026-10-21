"""End-to-end: the extension fills local fixture pages that imitate Greenhouse, Workday
(My Information, My Experience), an iCIMS iframe form and a generic careers form.

Two modes (both run by default):
  extension - Chromium loads the unpacked extension (--load-extension, headless); the test loads
              the packs through the real popup, presses "Fill this page" and reads the report the
              service worker stored. This is the real path: popup -> background -> every frame.
  inject    - the content files are added to every frame as page scripts and AutofillRun is
              called directly (no chrome.* APIs). A fallback for browsers that cannot load
              extensions headless, and a second check of the content code in the page's own world.

Packs are built with the real CLI (python -m auto_apply.fillpack) from the made-up candidate in
fixtures/candidate.json. Run with the auto-apply venv: ./run_tests.sh
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXT = HERE.parent
AUTO_APPLY = EXT.parent / "auto-apply"
FIXTURES = HERE / "fixtures"
CHROMIUM = os.environ.get("REA_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
CONTENT_FILES = re.findall(r"'(content/[^']+\.js)'", (EXT / "background.js").read_text())
MODES = [m for m in os.environ.get("AUTOFILL_E2E_MODES", "extension,inject").split(",") if m]

CANDIDATE = json.loads((FIXTURES / "candidate.json").read_text())
TAILORED = "Alex-Rivera-Acme-Data-Analyst.pdf"
DEFAULT = "Alex-Rivera-Resume.pdf"


def make_pdf(text: str) -> bytes:
    """A small valid one-page PDF (made-up content)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


@pytest.fixture(scope="session")
def packs(tmp_path_factory):
    d = tmp_path_factory.mktemp("packs")
    (d / "profile.json").write_text(json.dumps(CANDIDATE["profile"]))
    (d / "answers.json").write_text(json.dumps({"rules": CANDIDATE["rules"]}))
    (d / DEFAULT).write_bytes(make_pdf("Alex Rivera - resume"))
    (d / "job").mkdir()
    (d / "job" / "resume.pdf").write_bytes(make_pdf("Alex Rivera - tailored for Acme"))
    (d / "job" / "answers.json").write_text(json.dumps({"Why do you want to work here?": "Acme publishes open data I already use."}))
    run = functools.partial(subprocess.run, cwd=AUTO_APPLY, check=True, capture_output=True, text=True)
    py = sys.executable
    run([py, "-m", "auto_apply.fillpack", "profile", "--profile", str(d / "profile.json"),
         "--answers", str(d / "answers.json"), "--resume", str(d / DEFAULT), "--out", str(d / "profile-pack.json")])
    run([py, "-m", "auto_apply.fillpack", "job", "--pdf", str(d / "job" / "resume.pdf"),
         "--url", "https://acme.example.com/jobs/123/apply", "--title", "Data Analyst", "--company", "Acme",
         "--answers", str(d / "job" / "answers.json"), "--filename", TAILORED, "--runs", str(d),
         "--out", str(d / "job" / "job-pack.json")])
    return {"profile": d / "profile-pack.json", "job": d / "job" / "job-pack.json"}


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="session")
def server():
    handler = functools.partial(_Quiet, directory=str(FIXTURES))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


class ExtensionDriver:
    """The real thing: unpacked extension, popup, service worker."""

    mode = "extension"

    def __init__(self, pw, tmp, packs):
        self.packs = packs
        self.ctx = pw.chromium.launch_persistent_context(
            str(tmp / "profile"), executable_path=CHROMIUM, headless=True,
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"])
        sw = self.ctx.service_workers or [self.ctx.wait_for_event("serviceworker", timeout=15000)]
        self.ext_id = sw[0].url.split("/")[2]
        self.popup = self.ctx.new_page()
        self.popup_url = f"chrome-extension://{self.ext_id}/popup/popup.html"
        self.popup.goto(self.popup_url)
        self.popup.set_input_files("#profile-file", str(packs["profile"]))
        self.popup.wait_for_function("document.querySelector('#profile-status').textContent.includes('Alex Rivera')")

    def new_page(self):
        return self.ctx.new_page()

    def fill(self, page, job_pack: bool):
        tab_id = self.popup.evaluate(
            "url => chrome.tabs.query({}).then(ts => ts.find(t => t.url === url).id)", page.url)
        self.popup.goto(f"{self.popup_url}?tab={tab_id}")
        if job_pack:
            self.popup.set_input_files("#job-file", str(self.packs["job"]))
            self.popup.wait_for_function("document.querySelector('#job-status').textContent.includes('Data Analyst')")
        else:
            self.popup.evaluate("chrome.storage.local.remove('jobPack')")
            self.popup.reload()
        before = self.popup.evaluate("chrome.storage.local.get('lastRun').then(x => x.lastRun && x.lastRun.at)")
        self.popup.click("#fill")
        page.bring_to_front()  # timers in background tabs are throttled
        deadline = time.time() + 90
        while time.time() < deadline:
            run = self.popup.evaluate("chrome.storage.local.get('lastRun').then(x => x.lastRun)")
            if run and run["at"] != before and run["tabId"] == tab_id:
                break
            err = self.popup.evaluate("document.querySelector('#error').hidden ? '' : document.querySelector('#error').textContent")
            assert not err, err
            page.wait_for_timeout(200)
        else:
            raise AssertionError("fill did not finish in 90s")
        # The popup renders the same report.
        self.popup.bring_to_front()
        self.popup.wait_for_selector("#results:not([hidden])")
        run["popup_text"] = self.popup.inner_text("#results")
        run["popup_resume"] = self.popup.inner_text("#resume-status")
        return run

    def close(self):
        self.ctx.close()


class InjectDriver:
    """Fallback: the content files as page scripts in every frame, AutofillRun called directly."""

    mode = "inject"

    def __init__(self, pw, tmp, packs):
        self.browser = pw.chromium.launch(executable_path=CHROMIUM, headless=True)
        self.profile = json.loads(packs["profile"].read_text())
        self.job = json.loads(packs["job"].read_text())

    def new_page(self):
        return self.browser.new_page()

    def fill(self, page, job_pack: bool):
        frames = []
        for frame in page.frames:
            for f in CONTENT_FILES:
                frame.add_script_tag(path=str(EXT / f))
            rep = frame.evaluate("([p, j]) => AutofillRun({profilePack: p, jobPack: j})",
                                 [self.profile, self.job if job_pack else None])
            if rep["top"] or rep["items"] or rep.get("error"):
                frames.append(rep)
        return {"frames": frames, "popup_text": None}

    def close(self):
        self.browser.close()


@pytest.fixture(scope="module", params=MODES)
def driver(request, packs, tmp_path_factory):
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    cls = {"extension": ExtensionDriver, "inject": InjectDriver}[request.param]
    try:
        d = cls(pw, tmp_path_factory.mktemp(request.param), packs)
    except Exception as e:  # extensions cannot load in this browser: the inject mode still runs
        pw.stop()
        pytest.skip(f"{request.param} mode unavailable: {type(e).__name__}: {e}")
    yield d
    d.close()
    pw.stop()


# ---------- helpers ----------

def items(run):
    return [i for f in run["frames"] for i in f["items"]]


def item(run, pattern):
    hits = [i for i in items(run) if re.search(pattern, i["label"], re.I)]
    assert hits, f"no report item matching {pattern!r}: {[i['label'] for i in items(run)]}"
    return hits[0]


def assert_nothing_submitted(page):
    for frame in page.frames:
        if frame.evaluate("typeof window.__submitted") == "undefined":
            continue
        assert frame.evaluate("window.__submitted") is False, f"a form was submitted in {frame.url}"
        assert frame.evaluate("window.__forbiddenClicks") == [], f"forbidden button clicked in {frame.url}"


def assert_ask_reported(run, frame, selector, pattern):
    it = item(run, pattern)
    assert it["status"] == "needs" and it["reason"].startswith("ASK rule"), it
    assert frame.evaluate(f"document.querySelector({json.dumps(selector)}).value") == ""
    # The unanswered required field is outlined for the user.
    assert frame.evaluate(f"!!document.querySelector({json.dumps(selector)}).closest('[data-autofill=\"needs\"]') "
                          f"|| document.querySelector({json.dumps(selector)}).matches('[data-autofill=\"needs\"]')")


# ---------- the fixtures ----------

def test_greenhouse(driver, server):
    page = driver.new_page()
    page.goto(f"{server}/greenhouse.html")
    run = driver.fill(page, job_pack=True)
    state = page.evaluate("window.__state")
    # Text fields reached the "framework" state, not just the DOM (React value tracker).
    assert state["first_name"] == "Alex"
    assert state["last_name"] == "Rivera"
    assert state["email"] == "alex.rivera@example.com"
    assert state["phone"] == "+12175550100"
    assert state["question_1001"] == "https://www.linkedin.com/in/alex-rivera-example"
    assert state["question_1004"] == "Acme publishes open data I already use."  # per-job answer
    assert state["question_1002"] == "Yes"  # react-select combobox
    assert state["gender"] == "Decline To Self Identify"  # list rule, first wording that matches
    assert state["location"] == "Springfield, Illinois, United States"  # type-ahead, not West Springfield
    assert "question_1003" not in state  # sponsorship: ASK
    assert "preferred_name" not in state
    assert page.evaluate("document.querySelector('#veteran_status').selectedOptions[0].text") == "I am not a protected veteran"
    assert page.evaluate("document.querySelector('#gdpr_consent').checked") is True
    assert page.evaluate("document.querySelector('#resume').files[0].name") == TAILORED
    assert page.evaluate("document.querySelector('#resume').files[0].type") == "application/pdf"
    assert page.inner_text("#resume-name") == TAILORED
    assert_ask_reported(run, page.main_frame, "#question_1003", "sponsorship")
    assert item(run, "favourite dataset")["reason"] == "unknown required: no approved answer"
    assert item(run, "which tools")["reason"] == "no rule"
    assert item(run, "preferred first name")["status"] == "skipped"
    assert run["frames"][0]["ats"] == "greenhouse"
    assert page.locator("[data-autofill='filled']").count() >= 12
    assert_nothing_submitted(page)
    if run["popup_text"] is not None:
        assert "Needs you" in run["popup_text"] and "sponsorship" in run["popup_text"]
        assert TAILORED in run["popup_resume"]
    page.close()


def test_workday_my_information(driver, server):
    page = driver.new_page()
    page.goto(f"{server}/workday-info.html")
    run = driver.fill(page, job_pack=True)
    state = page.evaluate("window.__state")
    assert run["frames"][0]["ats"] == "workday"
    assert "applyFlowMyInfoPage" in run["frames"][0]["page"]
    assert state["source"] == "LinkedIn"  # search prompt
    assert state["previousWorker"] == "false"  # radio "No"
    assert state["country"] == "United States of America"  # dropdown + listbox
    assert state["state"] == "Illinois"  # appeared only after Country was chosen
    assert state["phoneType"] == "Mobile"
    assert state["name--legalName--firstName"] == "Alex"
    assert state["name--legalName--lastName"] == "Rivera"
    assert state["address--addressLine1"] == "100 Main St"
    assert state["address--city"] == "Springfield"
    assert state["address--postalCode"] == "62701"
    assert state["emailAddress--emailAddress"] == "alex.rivera@example.com"
    assert state["phoneNumber--phoneNumber"] == "2175550100"  # country code is its own field
    assert "phoneCode" not in state
    assert item(run, "country phone code")["reason"] == "kept the value already on the page"
    assert item(run, "this page only")["status"] == "info"
    assert page.evaluate("document.querySelector('#name--preferredCheck').checked") is False
    assert_nothing_submitted(page)
    page.close()


def test_workday_my_experience(driver, server):
    page = driver.new_page()
    page.goto(f"{server}/workday-exp.html")
    run = driver.fill(page, job_pack=True)
    state = page.evaluate("window.__state")
    entries = page.evaluate("""() => [...document.querySelectorAll('[data-automation-id^="workExperience-"]')].map(e => ({
        title: e.querySelector('[data-automation-id="jobTitle"]').value,
        company: e.querySelector('[data-automation-id="company"]').value,
        location: e.querySelector('[data-automation-id="location"]').value,
        current: e.querySelector('[data-automation-id="currentlyWorkHere"]').checked,
        from: [...e.querySelectorAll('[data-automation-id="formField-startDate"] input')].map(i => i.value),
        to: [...e.querySelectorAll('[data-automation-id="formField-endDate"] input')].map(i => i.value),
        description: e.querySelector('textarea').value}))""")
    assert entries == [
        {"title": "Product Analyst", "company": "Acme Analytics", "location": "Springfield, IL", "current": True,
         "from": ["06", "2024"], "to": ["", ""], "description": ""},
        {"title": "Data Analyst Intern", "company": "Springfield County Clerk", "location": "Springfield, IL",
         "current": False, "from": ["01", "2023"], "to": ["05", "2024"], "description": ""},
    ]
    assert state["workExperience-1.jobTitle.jobTitle"] == "Product Analyst"  # framework saw it
    edu = page.evaluate("""() => [...document.querySelectorAll('[data-automation-id^="education-"]')].map(e => ({
        school: e.querySelector('[data-automation-id="school"]').value,
        degree: e.querySelector('[data-automation-id="degree"]').textContent,
        gpa: e.querySelector('[data-automation-id="gpa"]').value,
        years: [...e.querySelectorAll('[data-automation-id="dateSectionYear-input"]')].map(i => i.value)}))""")
    assert edu == [{"school": "University of Springfield", "degree": "Master's Degree", "gpa": "3.8", "years": ["2022", "2024"]}]
    assert state["education-1.fieldOfStudy"] == "Statistics"  # typed search + Enter, exact option
    assert state["linkedin"] == "https://www.linkedin.com/in/alex-rivera-example"
    file_name = page.evaluate("document.querySelector('[data-automation-id=\"file-upload-input-ref\"]').files[0].name")
    assert file_name == TAILORED
    assert page.inner_text("#uploaded") == TAILORED
    assert page.evaluate("window.__websitesAdded") is None  # only work/education "Add" buttons are pressed
    assert item(run, r"work experience 2 › job title")["status"] == "filled"
    assert_nothing_submitted(page)
    page.close()


def test_icims_iframe(driver, server):
    page = driver.new_page()
    page.goto(f"{server}/icims-outer.html")
    page.wait_for_selector("#icims_content_iframe")
    frame = next(f for f in page.frames if "icims-form.html" in f.url)
    frame.wait_for_selector("#cp_form")
    run = driver.fill(page, job_pack=False)  # no job pack: the profile pack's default resume
    inner = next(f for f in run["frames"] if "icims-form.html" in f["frame"])
    assert inner["ats"] == "icims" and inner["top"] is False
    val = lambda sel: frame.evaluate(f"document.getElementById({json.dumps(sel)}).value")  # noqa: E731
    assert val("PersonProfileFields.FirstName") == "Alex"
    assert val("PersonProfileFields.LastName") == "Rivera"
    assert val("PersonProfileFields.Email") == "alex.rivera@example.com"
    assert val("PersonProfileFields.PhoneNumber") == "+12175550100"
    assert val("AddressStreet1") == "100 Main St"
    assert val("AddressCity") == "Springfield"
    assert val("AddressZip") == "62701"
    assert frame.evaluate("document.getElementById('AddressState').selectedOptions[0].text") == "Illinois"
    assert frame.evaluate("document.getElementById('rcf3048').selectedOptions[0].text") == "Yes"
    assert frame.evaluate("document.getElementById('ResumeUpload').files[0].name") == DEFAULT
    assert_ask_reported(run, frame, "#rcf3049", "sponsorship")
    assert item(run, "desired salary")["reason"] == "ASK rule"  # optional ASK: skipped, not answered
    assert val("rcf3050") == ""
    assert_nothing_submitted(page)
    if run["popup_text"] is not None:
        assert "iCIMS" in run["popup_text"] and "(iframe)" in run["popup_text"]
        assert "profile default" in run["popup_resume"]
    page.close()


def test_generic_form(driver, server):
    page = driver.new_page()
    page.goto(f"{server}/generic.html")
    run = driver.fill(page, job_pack=True)
    val = lambda sel: page.evaluate(f"document.querySelector({json.dumps(sel)}).value")  # noqa: E731
    assert run["frames"][0]["ats"] == "generic"
    assert val("#fn") == "Alex"  # label[for]
    assert val("[name=ln]") == "Rivera"  # wrapping label
    assert val("[name=contact_email]") == "alex.rivera@example.com"  # aria-labelledby
    assert val("[name=m]") == "+12175550100"  # aria-label
    assert val("[name=town]") == "Springfield"  # placeholder
    assert val("[name=li]") == "https://www.linkedin.com/in/alex-rivera-example"  # nearest text
    assert page.evaluate("document.querySelector('#ctry').selectedOptions[0].text") == "United States"
    assert page.evaluate("document.querySelector('[name=reloc][value=y]').checked") is True
    assert page.evaluate("document.querySelector('[name=agree]').checked") is True
    assert page.evaluate("document.querySelector('#cv').files[0].name") == TAILORED
    assert val("[name=honeypot_field]") == ""
    assert val("#cl") == ""
    assert item(run, "cover letter")["reason"] == "no rule"
    assert_ask_reported(run, page.main_frame, "#spons", "sponsorship")
    assert_nothing_submitted(page)
    page.close()


def test_lever(driver, server):
    page = driver.new_page()
    page.goto(f"{server}/lever.html")
    run = driver.fill(page, job_pack=True)
    val = lambda sel: page.evaluate(f"document.querySelector({json.dumps(sel)}).value")  # noqa: E731
    assert run["frames"][0]["ats"] == "lever"
    assert val("[name=name]") == "Alex Rivera"
    assert val("[name=email]") == "alex.rivera@example.com"
    assert val("[name=phone]") == "+12175550100"
    assert val("#location-input") == "Springfield, IL, USA"
    assert json.loads(val("[name=selectedLocation]"))["name"] == "Springfield, IL, USA"
    assert val("[name='urls[LinkedIn]']") == "https://www.linkedin.com/in/alex-rivera-example"
    assert page.evaluate("document.querySelector('[name=\"cards[a1][field1]\"][value=Yes]').checked") is True
    assert page.evaluate("[...document.querySelectorAll('[name=\"cards[a1][field0]\"]')].some(r => r.checked)") is False
    assert page.evaluate("document.querySelector('#resume-upload-input').files[0].name") == TAILORED
    it = item(run, "sponsorship")
    assert it["status"] == "needs" and it["reason"].startswith("ASK rule")
    assert_nothing_submitted(page)
    page.close()


def test_ashby(driver, server):
    page = driver.new_page()
    page.goto(f"{server}/ashby.html")
    run = driver.fill(page, job_pack=True)
    state = page.evaluate("window.__state")
    assert run["frames"][0]["ats"] == "ashby"
    assert page.evaluate("document.querySelector('#_systemfield_name').value") == "Alex Rivera"
    assert page.evaluate("document.querySelector('#_systemfield_email').value") == "alex.rivera@example.com"
    assert page.evaluate("document.querySelector('#_systemfield_resume').files[0].name") == TAILORED
    assert state["q_auth"] == "Yes"
    assert state["q_years"] == "No"  # asks 5 years, the years rule says 3
    assert "q_spons" not in state
    it = item(run, "sponsorship")
    assert it["status"] == "needs" and it["reason"].startswith("ASK rule")
    assert_nothing_submitted(page)
    page.close()
