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
```

`audit` exits 1 when a resume fails, so a build script can stop on it.

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
