---
name: tsenta-apply
description: Apply to jobs through Tsenta with a resume Claude tailored. Use when Sai asks to find jobs and apply, run the auto-apply pipeline, apply to a specific posting or Tsenta job id, or test the pipeline. Tsenta searches, Claude tailors the PDF (sai-resume-tailor), guard checks run, then Tsenta submits the PDF verbatim.
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

## 4. Upload
1. `request-resume-upload` → `uploadId`, `uploadUrl` (expires in ~5 minutes).
2. `cli upload runs/<job>/resume.pdf '<uploadUrl>'` → expect HTTP 200.
3. `check-custom-resume { uploadId }` → confirms a valid PDF.

## 5. Apply (after Sai's go-ahead)
`apply-with-custom-resume { jobId | url, uploadId, profile: <contents of runs/profile.json> }`.
Add `coverLetter: { text }` only if Sai asked for one. Do not use `apply-to-job` here: it
re-tailors with Tsenta's optimizer and, with autoApproveResume off, waits for approval.

## 6. Record and follow up
- `cli record --company … --title … --url … --job-id … --application-id … --pdf runs/<job>/resume.pdf --status <status>`
- `get-application-status { applicationId }`: relay `statusLabel`. `PENDING_SUBMIT_REVIEW`
  with `missingRequired` → ask Sai for those answers. FAILED → relay `statusMessage`.
- Report per job: company, role, status, gate warnings, gaps from the tailoring note.
