# Job-search agent toolkit

Deterministic helpers for an agent system that scouts jobs, builds an honest tailored resume for
each one, and applies only after a human says yes in a Notion tracker. The model does the
reading and writing; everything that can be a rule is a script here, so it costs no tokens and
gives the same answer every time.

## What's here

| Path | What it does |
|---|---|
| `jobagent/audit.py` | Checks a built resume: page count, do-not-claim terms (read from the facts file), copies of the layout example, reused bullets without a success record, and how many job requirements have real evidence |
| `jobagent/gaps.py` | Counts the skills job postings ask for that the resume can't honestly claim, across all job maps |
| `jobagent/bullets.py` | Bullet library: when an application succeeds, finds the same wording across every sent resume (from the PDFs) to count uses and successes, and releases a wording for reuse only with a proven success rate |
| `jobagent/screen.py` | Knockout screen run before any resume is built: citizenship, clearance, sponsorship (only when the person needs it), OPT exclusions (only when `work_authorization.on_opt` is true), years asked, degree, senior titles, student-only |
| `jobagent/score.py` | Fit score 0-100: match (required and preferred coverage, posting keywords in the resume) plus hireability (level, PDF readability, freshness, hiring signal). Before a build it is a cheap gate; after a build it decides auto-apply, wait for the person, or skip |
| `jobagent/outcomes.py` | Outcome log (`work/outcomes.csv`, one row per sent application with its score parts) and a calibration report: base rate with a Wilson interval, reply rate by score band, AUC, counts by role family and source |
| `notebooks/01_score_calibration.ipynb` | Checks whether the score predicts replies: censoring, bootstrap AUC, logistic regression, calibration, which parts matter, cost-based thresholds, power. Runs on a synthetic demo log until the real one exists |
| `config.example.json` | Per-person settings the screen and score read: experience, degrees, work authorization, target role families, thresholds, daily cap. Copy it to `work/config.json` and fill it in |
| `prompts/cycle.md` | The steps one scheduled agent run follows, starting with a cheap gate |
| `tests/` | Tests with synthetic fixtures |

Personal data (the facts file, resumes, job maps, the bullet library, ledgers) is never stored
in this repo. It lives in Notion and in a local working folder (`agent/work/`, git-ignored).

## Usage

```
cd agent
python -m jobagent audit resume.tex --facts facts.md --example example.tex \
    --pdf resume.pdf --jd-map jd_map.md --others resumes/ --approved work/bullets.json
python -m jobagent gaps resumes/*/jd_map.md
python -m jobagent bullets scan work/sent --success APP1,APP2 --families APP1=ai --out work/bullets.json
python -m jobagent bullets reusable work/bullets.json --family ai
python -m jobagent rank jds/*.md --config work/config.json --facts facts.md      # before building
python -m jobagent outcomes add APP7 --score-json work/scores/acme.json --source tsenta  # when sent
python -m jobagent outcomes set APP7 interview                                          # when heard back
python -m jobagent outcomes report                                                      # calibration so far
python -m jobagent score jds/acme.md --config work/config.json --facts facts.md \
    --jd-map resumes/acme/jd_map.md --tex resumes/acme/resume.tex --pdf resumes/acme/resume.pdf
```

`audit` exits 1 when a resume fails, so a build script can stop on it.

## The score

| Part | Points | Before a build | After a build |
|---|---:|---|---|
| Required requirements covered | 30 | estimated from tools and domain words in the facts file | share of required job-map rows with real evidence |
| Posting keywords in the resume | 15 | facts file | final resume |
| Preferred requirements covered | 5 | neutral 2.5 | preferred job-map rows |
| Level (role family, years asked) | 15 | same | same |
| PDF readable in order (name, email, section order) | 10 | assumed | checked with `pdftotext` |
| Freshness (days since posted) | 10 | same | same |
| Active-hiring signal from research (0-1) | 15 | neutral 7 | neutral 7 unless given |

Any knockout makes the score 0. Thresholds come from the config (defaults: build 50, review 65,
auto 80). Unknown freshness and signal score in the middle, so auto-apply needs positive
evidence. The weights are a starting point: once outcomes (interviews, rejections) are tracked,
they can be fitted from real results.

## Does the score work?

Every sent application is logged with its score parts, and every reply, rejection or silence
is its outcome. A reply, screen, interview or offer is positive. A rejection, or no reply after
30 days, is negative. Anything newer is pending and left out, so recent applications don't
count as failures before employers have had time to answer. `outcomes report` and the notebook
show whether higher scores really get more replies.

The demo run in the notebook shows the catch. Even with a real effect built in (odds x1.9 per 10
points), 121 settled applications give an AUC interval of about 0.44 to 0.73, which still
includes a coin flip. The power simulation puts 80% power near 400 settled applications. So the
thresholds stay where they are until the report says there's enough data. The results
table below gets filled in from real outcomes.

| Date | Settled | Positive | Base rate (95% CI) | AUC (95% CI) | Change made |
|---|---:|---:|---|---|---|
| _pending first outcomes_ | | | | | |

## The reuse rule

`work/sent/` holds one PDF per sent application, named `<application id>.pdf` (the agent
downloads them from the tracker). Two bullets count as the same wording at 0.8 similarity.

A bullet's wording may appear on more than one resume only after it has been used at least
twice and at least one of those applications got a positive outcome (interview, offer, or a
recruiter reply), with a success rate at or above the average for all applications. Until
then, every resume gets fresh wording.

## Tests

```
cd agent && python -m pytest -q tests
```
