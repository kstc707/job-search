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

## Flow

```
get-job-recommendations ─▶ get-jobs-by-ids ─▶ sai-resume-tailor ─▶ resume.pdf
                                                                       │
             cli gate (dedupe · daily cap · never-claim · banned phrases · fixed titles)
                                                                       │ pass
request-resume-upload ─▶ cli upload (PUT to presigned URL) ─▶ check-custom-resume
                                                                       │
             apply-with-custom-resume { jobId|url, uploadId, profile } ─▶ cli record
```

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

## Setup

```bash
cd projects/auto-apply
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Needs `pdftotext` (poppler-utils) for `gate`, and LaTeX for the resume build
(`texlive-latex-base texlive-latex-extra texlive-fonts-recommended`).

Personal data (profile, instructions, resumes, job descriptions, ledger) lives in `runs/`,
which is git-ignored because this repository is public.

## Tests

Offline, with a made-up candidate:

```bash
.venv/bin/python -m pytest
```
