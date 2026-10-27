# Auto Apply: Tsenta search → Claude tailoring → Tsenta submit

An agent pipeline for applying to jobs: [Tsenta](https://tsenta.com)'s MCP server finds
postings and submits applications, Claude writes a resume tailored to each posting, and
this package runs the deterministic checks in between, so nothing fabricated, duplicated
or off-policy reaches an employer.

The agent steps are in [`.claude/skills/tsenta-apply/SKILL.md`](../../.claude/skills/tsenta-apply/SKILL.md).

## Why not Tsenta's built-in Auto Apply?

Tsenta can apply on a schedule by itself, but it tailors with its own optimizer and needs
the Power plan. The per-job MCP tools work on every plan, and two of them matter here:

| Tool | Resume that reaches the employer | Form fields filled from |
|---|---|---|
| `apply-to-job` | Tsenta re-tailors your saved resume (HONEST/AGGRESSIVE), or sends it as-is with `OFF` | Tsenta profile |
| `apply-with-custom-resume` | **Your PDF, verbatim** (no re-render) | The `profile` JSON you pass |

This pipeline uses `apply-with-custom-resume`, so Claude's resume is exactly what gets sent.
Two consequences drive the design:

1. **The PDF is final once uploaded.** A hallucinated tool or a changed job title cannot be
   caught later, so `gate` checks the PDF's extracted text first.
2. **Form answers come from the profile, not the PDF.** `profile` builds and validates that
   JSON, and `gate` warns when profile and resume disagree (e.g. different emails).

## Workflow

```
 FIND            Tsenta get-job-recommendations → get-jobs-by-ids (full JD)
   │             filter: supported ATS, YOE, degree, sponsorship, eligibility
   ▼
 TAILOR          Claude + sai-resume-tailor → runs/<job>/resume.pdf
   │             (evidence map → LaTeX → build → visual check → originality)
   ▼
 GATE            cli gate: dedupe · daily cap · never-claim · banned phrases · fixed titles
   │             blocked → fix the resume, never the rules
   ▼
 ROUTE by ATS ───────────────────────────────┬──────────────────────────────────────
   │ Greenhouse, Ashby (Lever: built, on test) │ everything else (Workday, Oracle,
   ▼                                          ▼  iCIMS, SuccessFactors, SmartRecruiters…)
 FILLER (ours)                              TSENTA
   plan  : read form from public API,         request-resume-upload → cli upload
           answer each field from approved    → check-custom-resume
           data; unknown required → STOP      → apply-with-custom-resume
   fill  : real browser, read-back verify,      (PDF verbatim, form from profile)
           screenshot                         
   review: Sai approves the screenshot        
   submit: --submit (captcha → hand to Sai)   
   │                                          │
   └──────────────────┬───────────────────────┘
                      ▼
 RECORD          cli record → ledger.jsonl ; Tsenta get-application-status for Tsenta jobs
```

Why two submit paths: our filler is free, shows every answer before sending and keeps the
answers under your control, but only covers public, login-free forms. Tsenta handles the
login-based ATSes and costs one credit per application.

## Running a whole cycle as a Workflow

[`prompts/v2-cycle.md`](prompts/v2-cycle.md) is one run of the job agent. The same run is saved as a
multi-agent workflow in [`.claude/workflows/job-search.js`](../../.claude/workflows/job-search.js).
Ask Claude Code to "run the job-search workflow" with:

```json
{"date": "2026-10-27", "mode": "dry"}
```

`mode: "dry"` (the default) builds up to 3 resumes and sends nothing; `mode: "live"` also sends the rows
Sai approved on the review page and builds up to 8 (`maxJobs` overrides either cap).
`sources` picks where jobs come from (default `["boards", "jobright"]`; `"tsenta"` and `"indeed"` are
opt-in), and `tsenta: true` lets jobs outside the filler's ATSes go through `apply-with-custom-resume`.
Without it those jobs are marked for Sai to send by hand.

### Job sources

- **Career pages** (`auto_apply/v2/boards.py`, list in [`watchlist.json`](watchlist.json)): most
  employers' ATSes publish their board as public JSON, so the watcher reads it directly. No
  scraping, and every job comes with the employer's own apply URL. It keeps analyst-type titles and
  remembers what it has seen (`runs/v2/boards_seen.json`), so each scan returns only new postings.
  `boards find` looks a company up on the boards whose URL can be guessed from its name. That is how a
  Jobright or Indeed job becomes an employer URL the filler can open.
- **Jobright** (`auto_apply/v2/apify.py`): Jobright has no API, so searches run through the Apify actor
  `jobscrawler/jobright-scraper` (about $0.004 a job; `--budget-usd` refuses runs above a cap). The token is
  read from the `APIFY_TOKEN` environment variable; add it in the cloud environment's settings (never in
  the repo). Without it, the workflow reads Jobright's alert emails from Gmail instead.

Why Tsenta became opt-in: an audit of all 471 Tsenta applications (2026-10-27) found that the 100 sent
with `apply-with-custom-resume` reached employers as our PDF, unchanged. The 371 sent from the Tsenta app or
`apply-to-job` were rebuilt by Tsenta's optimizer, which added tools that aren't in the profile.

| Stage | Agents | v2 step |
|---|---|---|
| Sync | 1 | setup, Tsenta inbox → tracker outcomes |
| Apply (live only) | 1 | send approved rows (filler or `apply-with-custom-resume`) |
| Find | 1 per source, in parallel | career-page watcher, Jobright (Apify); Tsenta/Indeed opt-in |
| Screen | 1 | dedupe vs tracker, `v2.target`, employer apply URL, read postings, skip rules |
| Build | 1 per job, in parallel | sai-resume-tailor + `v2.ats_check` |
| Review | 1 for all resumes | red-team: 3 reasons to reject each |
| File | 1 | fixes, filler plan, drafted answers, Notion rows (Submit? No) |
| Report | 1 | Run Log entry on the memory page |

The rules stay in `v2-cycle.md`; the script only fixes the order, the parallelism and what each stage
hands to the next. The first stage copies Sai's decisions from the Notion memory page into
`runs/v2/memory.md`, so later stages don't each re-read Notion. The token line in the report uses the
workflow's output-token counter per stage, which is not the same measure as the `subagent_tokens`
baseline from 2026-10-19.

## Modules

- `auto_apply/guard.py`: parses Tsenta's `resumeInstructions` ("Never claim: A, B/C." and
  quoted phrases after "never"/"no"/"do not") into rules, then checks resume text:
  never-claim tools and banned phrases are errors; each profile job title must appear
  verbatim (error); employers and the contact email are checked as warnings.
- `auto_apply/profile.py`: extracts the profile from a `get-resume-profile` response and
  lists empty required fields.
- `auto_apply/upload.py`: validates the PDF (header, trailer, 5 MB limit) and PUTs it to
  the presigned URL, so the bytes never pass through the agent's context.
- `auto_apply/ledger.py`: JSONL log; dedupes on normalized URLs (tracking parameters
  stripped) and job ids; counts today's applications for the cap.
- `auto_apply/cli.py`: `profile`, `gate`, `upload`, `record`, `list`.
- `auto_apply/v2/boards.py`: career-page watcher (`scan`, `add`, `find`) over public ATS job-board APIs.
- `auto_apply/v2/apify.py`: Jobright searches through Apify, normalised to the v2 job shape.
- `auto_apply/filler/`: our own form filler (Greenhouse, Lever, Ashby).
  - `schema.py` reads the form from `boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}?questions=true`
    (field names there are the DOM ids on the form, so nothing is guessed from HTML).
  - `answers.py` resolves each field from the profile, `runs/answers.json` rules and optional
    per-job answers. `"ASK"` rules and unknown required questions block the run.
  - `greenhouse.py` fills with Playwright (text, file upload, type-ahead selects, checkboxes),
    reads every value back, screenshots, and submits only with `--submit`.
  - `domform.py` handles Lever and Ashby, which publish no form API: it opens the apply page,
    reads every question from the page (one small selector profile per system), and fills
    text, files, dropdowns, radios, checkboxes, Ashby Yes/No buttons and location look-ups.
    Name, email and phone are recognised by label; everything else uses the same answer rules.
  - `cli.py`: `python -m auto_apply.filler.cli plan|fill <job url> --pdf <resume> [--submit]`.
    `--test-fill` fills a blocked form for testing and can never be combined with `--submit`.
    When a form is blocked, the open questions (with options) are written to
    `<resume folder>/questions.json` for drafting; drafted answers in `answers.json` there are
    checked against the never-claim list and banned phrases before any form is opened.

The design follows how client-side autofill tools are built (per-ATS form locators, a
field-category/answer layer, events that React forms register), learned by static analysis
of public extensions; the code here is written from scratch.

## Setup

```bash
cd projects/auto-apply
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Needs `pdftotext` (poppler-utils) for `gate`, Chromium for the filler (set `REA_CHROMIUM` to its path), and LaTeX for the resume build
(`texlive-latex-base texlive-latex-extra texlive-fonts-recommended`).

Personal data (profile, instructions, resumes, job descriptions, ledger) lives in `runs/`,
which is git-ignored because this repository is public.

## Tests

Offline, with a made-up candidate:

```bash
.venv/bin/python -m pytest
```
