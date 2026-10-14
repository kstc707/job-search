---
name: tsenta-apply
description: Apply to jobs with a resume Claude tailored. Use when Sai asks to find jobs and apply, run the auto-apply pipeline, apply to a specific posting or Tsenta job id, or test the pipeline. Tsenta searches, Claude tailors the PDF (sai-resume-tailor), guard checks run, then Greenhouse jobs go through our own form filler (review before submit) and everything else through Tsenta, which submits the PDF verbatim.
---

# Tsenta apply pipeline

Code and background: `projects/auto-apply/` (README explains why each step exists).
Run CLI commands from `projects/auto-apply` with `.venv/bin/python -m auto_apply.cli …`
(create the venv with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
All personal data goes in `projects/auto-apply/runs/` (git-ignored; the repo is public).

Submitting is real and uses an application credit. Never call `apply-with-custom-resume`
without Sai's go-ahead for that job, or a batch go-ahead he gave in this conversation.

## 0. Session setup (once per session)
1. `get-apply-preferences` → write `resumeInstructions` to `runs/instructions.txt`.
2. `list-resume-profiles`, then `get-resume-profile` for the profile to apply with → save the
   raw response to `runs/profile_raw.json` → `cli profile runs/profile_raw.json`.
   Exit 2 lists missing fields: stop and tell Sai.
3. Put the facts file's "Do not claim" terms in `runs/never_claim.txt` (comma-separated).
4. `get-auto-apply-state` only if Sai asks about Tsenta's own scheduled Auto Apply (it needs
   the Power plan; this pipeline does not).

## 1. Find jobs
- `get-job-recommendations` (e.g. `limit: 30`, `datePosted: "7d"`, roleFamilies DATA_SCIENCE,
  `locations: ["country:US"]`). Keep only `isSupportedAts: true`. Drop jobs whose
  `yearsOfExperienceMin`, degree or sponsorship rules he fails; flag borderline ones.
- `get-jobs-by-ids` (≤20) for full descriptions. For a pasted URL use `fetch-job-description`.

## 2. Tailor
For each chosen job make `runs/<yyyy-mm-dd>-<company>-<role>/` and follow the
`sai-resume-tailor` skill there (jd_map.md → resume.tex → build.sh → visual check).

## 3. Gate (must pass)
`cli gate runs/<job>/resume.pdf --url <posting url> --job-id <tsenta id>`
Exit 2 = blocked: duplicate, daily cap, a never-claim tool, a banned phrase or a changed
job title. Fix the resume (never the rules) and rerun. Read every WARNING; the
`contact-mismatch` warning means the form will use a different email than the PDF.

## 4. Route by ATS
- `atsType == "greenhouse"` and a hosted `*.greenhouse.io` URL → **our filler** (step 5a).
- Anything else, or a Greenhouse job only reachable through a career page → **Tsenta** (5b).

## 5a. Our filler (Greenhouse)
1. If this resume was not built by the cycle (so `jobagent audit` never ran on it), run the audit first
   (cycle step 5 command): it catches copies of the example resume and bullets repeated from
   earlier resumes, which `cli gate` does not check.
2. `.venv/bin/python -m auto_apply.filler.cli plan <url> --pdf runs/<job>/resume.pdf`
   Exit 3 lists required questions without an approved answer. Ask Sai; save one-off answers
   in `runs/<job>/answers.json` (`{"exact label": "answer"}`), standing ones as rules in
   `runs/answers.json`. Never invent answers. Free-text answers: draft from facts.md only,
   show Sai, then save.
3. `… filler.cli fill <url> --pdf …` → fills, reads back, writes `runs/<job>/form-filled.png`.
   Show Sai the screenshot and the plan table.
4. Only after Sai approves that job: `… filler.cli fill <url> --pdf … --submit`.
   "NOT SUBMITTED" after a captcha → give Sai the URL to finish by hand, or route to 5b.

## 5b. Tsenta (everything else)
1. `request-resume-upload` → `uploadId`, `uploadUrl` (expires in ~5 minutes).
2. `cli upload runs/<job>/resume.pdf '<uploadUrl>'` → expect HTTP 200.
3. `check-custom-resume { uploadId }` → confirms a valid PDF.
4. After Sai's go-ahead: `apply-with-custom-resume { jobId | url, uploadId, profile: <contents
   of runs/profile.json> }`. Add `coverLetter: { text }` only if Sai asked for one. Do not use
   `apply-to-job`: it re-tailors with Tsenta's optimizer and waits for approval.

## 6. Record and follow up
- Record every submission, with `--note filler` or `--note tsenta`:
  `cli record --company … --title … --url … --job-id … --application-id … --pdf runs/<job>/resume.pdf --status <status>`
- `get-application-status { applicationId }`: relay `statusLabel`. `PENDING_SUBMIT_REVIEW`
  with `missingRequired` → ask Sai for those answers. FAILED → relay `statusMessage`.
- Report per job: company, role, status, gate warnings, gaps from the tailoring note.
