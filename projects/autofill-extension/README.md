# Apply Autofill (Chrome extension)

Fills job applications in your own browser from data you approved: your profile, your answer
rules, and a resume Claude tailored for the job. It covers the applicant tracking systems (ATS)
the cloud filler in [`../auto-apply`](../auto-apply) cannot reach because they need a login or a
real browser session: Workday, iCIMS, SmartRecruiters, Oracle Cloud HCM, Paylocity, UKG/UltiPro,
Dayforce, ADP and BambooHR. It also handles Greenhouse, Lever, Ashby and has a generic reader for
everything else.

**It never submits.** It fills the page you are looking at, outlines what it filled and what
still needs you, and stops. Next, Continue, Apply and Submit are always your clicks.

## Install (once)

1. Open `chrome://extensions` and switch on **Developer mode** (top right).
2. Click **Load unpacked** and pick this folder (`projects/autofill-extension`).
3. Pin "Apply Autofill" from the puzzle-piece menu so its button is always visible.

No build step: plain JavaScript, Manifest V3.

## Make the packs

Packs are JSON files built by the auto-apply package, which validates them first. They hold
personal data, so keep them in `projects/auto-apply/runs/` (git-ignored).

```bash
cd projects/auto-apply

# Profile pack: once, and again whenever the profile or rules change.
.venv/bin/python -m auto_apply.fillpack profile \
    --profile runs/profile.json --answers runs/answers.json \
    [--resume runs/default-resume.pdf] --out runs/profile-pack.json

# Job pack: one per application, next to the tailored resume.
.venv/bin/python -m auto_apply.fillpack job \
    --pdf runs/<job>/resume.pdf --url "<apply url>" --title "Data Analyst" --company "Acme" \
    [--answers runs/<job>/answers.json] [--filename First-Last-Resume.pdf] \
    --out runs/<job>/job-pack.json
```

What gets checked: the profile has a name and email; every rule has a `match` regex that both
Python and the extension's JavaScript can run, and an `answer` (text, a list of alternative
wordings, `"ASK"`, or `null`); the PDF starts with `%PDF-`, ends with `%%EOF` and is under 5 MB;
per-job answers do not claim a skill on the never-claim list (same check as `filler.cli fill`).

| Pack | Contents | Loaded |
|---|---|---|
| Profile pack | `profile` (the Tsenta-shaped profile JSON), `rules` (the ordered list from `runs/answers.json`), optional `defaultResume` | once; stays until you load another |
| Job pack | `job` (url, title, company), `answers` (`{"exact question label": answer}`), `resume` (tailored PDF, base64) | per job; **Clear** removes it |

The resume uploaded is the job pack's PDF, or the profile pack's default resume when no job pack
is loaded.

## Use it

1. Load the profile pack (popup → Profile pack → **Load**). Once.
2. For each application, load its job pack (popup → Job pack → **Load**). The popup shows the
   job and the resume file, and warns if the pack's URL is for a different site than the tab.
3. Open the application page (sign in / create the account yourself where needed) and press
   **Fill this page**.
4. Read the result list: **Needs you** first (ASK questions, required questions with no
   approved answer, options that did not match, captchas, sign-in steps), then **Filled** and
   **Skipped** with the reason (`ASK rule`, `no rule`, `kept the value already on the page`...).
   On the page, filled fields have a faint green outline and unfilled required ones a red one.
5. Answer the red ones, check everything, and click Next / Submit yourself. On multi-page forms
   (Workday, Oracle, iCIMS) press **Fill** again on each page.

## How answers are chosen

`content/answers.js` is a line-by-line port of `auto_apply/filler/answers.py`, so both fillers
answer every question the same way:

1. **Files**: a resume / cover-letter input gets the pack's PDF.
2. **Profile**: Greenhouse field names (`first_name`, `email`...), then anchored labels
   ("Full name", "Email", "Phone", "Zip", "Address"). "Preferred name" is not "Name".
3. **Years questions**: "at least N years of..." is answered "No" when N is more than the
   years-of-experience rule; fewer is asked (it may be skill-specific).
4. **Per-job answers** by exact label (case and punctuation ignored), then the **rules** in
   order: first regex that matches the label wins. `"ASK"` is never answered (required → Needs
   you, optional → skipped). A list is alternative wordings: the first one that names exactly
   one option is picked. Option matching is exact, then prefix, then whole words ("No" never
   matches "I am **no**t a veteran"); if two options tie, nothing is picked.

Additions the browser needs, used only where `answers.py` would say "no approved answer"
(so they never contradict it): "Address Line 1/2" get the street only; City, State, Country,
County, LinkedIn, GitHub and Website come from the profile; dropdowns whose options appear only
when opened and single consent checkboxes are handled. `tests/test_parity.py` runs 40 questions
through both engines and requires identical results.

Rules are Python regexes. The extension translates the Python-only syntax (`(?i)` at the start,
`(?P<name>...)`, `\A`, `\Z`); lookbehind such as `(?<!trans)gender` works as is. `fillpack`
rejects what JavaScript cannot run (possessive quantifiers, atomic groups, inline flags mid-pattern).

## What each adapter covers

The adapter is chosen by the frame's hostname, then by page markup, else the generic reader.

| ATS | How it reads the form | Fills |
|---|---|---|
| **Workday** (`*.myworkdayjobs.com`, `*.myworkday.com`) | each `[data-automation-id="formField-…"]` container: its `<label>`/`<legend>` and control | text; dropdown buttons (opens the listbox, picks the option); search prompts ("How did you hear", phone code: click, or type + Enter, pick); radios; checkboxes; month/year dates. Country first, so State appears. **My Experience**: Work Experience and Education entries from the profile's `workExperience` / `education`, pressing the section's **Add** button per missing entry (title, company, location, "I currently work here", from/to; school, degree, field of study, GPA, years). Resume into the file-upload input. Phone number without `+1` (Workday asks the code separately). Current page only. |
| **Greenhouse** (`*.greenhouse.io`, embedded `#grnhse_app`) | generic reader on the application form; ids are Greenhouse field names | text, react-select dropdowns (EEO, yes/no), location type-ahead, checkboxes, native selects, resume |
| **Lever** (`jobs.lever.co`) | `li.application-question` + `.application-label`, as `domform.py` | text, radios/checkboxes (side groups become their own question, as in Python), location look-up (`selectedLocation`), resume |
| **Ashby** (`jobs.ashbyhq.com`) | `.ashby-application-form-field-entry`, as `domform.py` | text, Yes/No button pairs, selects, comboboxes, resume |
| **iCIMS** (`*.icims.com`) | the form is an iframe: Fill runs in every frame and the iframe's own host picks this adapter; generic reader inside it | text, native selects, radios, resume. Sign-in pages are reported. |
| **SmartRecruiters** | generic reader, also inside open shadow roots (their web components) | text, selects, comboboxes, files |
| **Oracle Cloud HCM** (`*.oraclecloud.com`) | `.input-row` containers with `.input-row__label`, Yes/No pills; generic reader for the rest | text, comboboxes, Yes/No, files. The emailed code step is reported. |
| Paylocity, UKG/UltiPro, Dayforce, ADP, BambooHR | named in the popup, generic reader | as generic |
| **Generic** (anything else) | each control's label from `label[for]`, `aria-labelledby`, wrapping `<label>`, `aria-label`, nearest text, `placeholder`; radio/checkbox groups from `<legend>` / role=radiogroup / nearby text | text, textareas, native selects, radios, checkbox groups, single consent boxes, comboboxes, location type-aheads, files. Skips search boxes, nav/header/footer, honeypots. |

Value setting works with React, Angular and Knockout forms: the native value setter (bypassing
React's value tracker), then `input`, `change` and `blur` events. Type-aheads get real per-key
`keydown`/`input` events; options are clicked with pointer and mouse events. Files go in through
a `DataTransfer`, like a drag and drop.

## Limits

- **Never clicks Submit / Next / Apply / Continue / Review / Sign in.** Every click goes through
  a guard that refuses those buttons, and form submissions are cancelled while a fill runs.
  The only buttons it presses are dropdowns, options, Yes/No answers and Workday's
  Work Experience / Education **Add**.
- **Captchas**, **account creation, sign-in and email verification** (Workday, iCIMS, Oracle's
  emailed code) are yours; the popup lists them under Needs you.
- Workday: one page per Fill. Hierarchical "How did you hear" lists are only matched at the top
  level or via search. Date inputs are typed digit by digit; a tenant with a calendar-only
  picker may need a manual date. Extra entries Workday parsed from your resume beyond the
  profile's count are reported, never deleted. Skills, Websites, Languages and Certifications
  sections are left alone.
- SmartRecruiters / Oracle / UKG / Paylocity / Dayforce / ADP / BambooHR were built from their
  public markup patterns and checked only against the generic fixtures here, not live tenants:
  expect some Needs you items the first time on each.
- Closed shadow roots and cross-origin canvases cannot be read.
- Free-text questions are never written by the extension: draft them into the job pack's
  answers (`filler.cli` writes the open questions to `questions.json` for that).

## Privacy

- Packs live in `chrome.storage.local` in this browser profile; nothing is synced or uploaded.
- The extension makes **no network calls** (no `fetch`, no analytics). Content scripts are
  injected only into the tab you press Fill on, at that moment (`scripting` + `activeTab`; the
  `<all_urls>` host permission is needed because ATS forms live in iframes on other hosts).
- The resume leaves your machine only when you submit the form.

## Files

```
manifest.json            MV3 manifest
background.js            service worker: injects the content files into every frame, runs the fill, stores the report
popup/                   popup.html / popup.js / popup.css: load packs, Fill, results
content/answers.js       the answer engine (pure; also runs under Node)
content/dom.js           value setting, labels, dropdowns, files, highlighting, the submit guard
content/collect.js       question readers (generic and per-container) and fillField
content/adapters/*.js    workday, greenhouse, lever-ashby, icims, smartrecruiters, oracle, generic (+ named generic hosts)
content/content.js       AutofillRun: detect, notices, fill, report
tests/                   unit, parity and end-to-end tests (see below)
```

## Tests

```bash
projects/autofill-extension/tests/run_tests.sh        # extension tests
projects/autofill-extension/tests/run_tests.sh --all  # + the auto-apply pytest suite
```

- `answers.test.js` (`node --test`): the answer engine with the made-up candidate in
  `tests/fixtures/candidate.json` (ASK rules, list alternatives, `(?<!trans)gender`, years
  questions, per-job answers, files, regex translation, location and date helpers).
- `test_parity.py`: the same 40 questions through `answers.py` and `answers.js`; identical
  status, value, source and note.
- `test_e2e.py` (Playwright): builds packs with `fillpack`, loads the unpacked extension in
  headless Chromium, loads the packs through the popup, presses Fill and checks the fixture
  pages: Greenhouse, Workday My Information and My Experience, an iCIMS form in an iframe, a
  generic form, Lever and Ashby. It asserts the values the page's own scripts registered, the
  uploaded file name, that no submit / next button was clicked and no form submitted, and that
  ASK questions are reported and left empty. The same pages also run with the content files
  injected straight into the page (`AUTOFILL_E2E_MODES=inject` runs only that mode).

The fixture pages imitate each system's markup and widget behaviour (React's value tracker,
react-select, Workday's listbox and search prompt, a delayed location look-up); they are not
copies of any vendor's code.
