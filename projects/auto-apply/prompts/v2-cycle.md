# Job agent v2: one run

Goal: **a callback from a person.** Fewer, better-aimed applications: entry-level analyst roles,
Sai's locations first, fresh postings, a checked resume, and nothing sent without Sai's approval.

Read first, every run: the Notion memory page `3f755fb9-8924-81a1-b4c8-fe6cc3265094`
(decisions there are Sai's and override this file), then this file.

**Mode:** if the message that started this run says `DRY_RUN`, do steps 0–5 and 7, build at
most 3 resumes, and send nothing (skip step 6).

## Fixed IDs
- Tracker data source: `collection://3957830f-6f7e-46ae-8109-a5845caa5ef2`
- Views (use these to READ the tracker; they don't count against Notion's query allowance):
  all rows `view://3fe55fb9-8924-818f-b009-000c503e0b57`, review queue `view://3fe55fb9-8924-811d-b461-000cabb1075f`.
  Do not use SQL or rows-mode queries on the tracker: the plan's allowance runs out.
- Sai's review page: https://claude.ai/artifact/Kww5m3d7yNZZMvbSELseF9

## Hard rules
1. **Never set `Submit?` or `Approved at`, and never revert them.** Only Sai's review page writes
   them. Every Notion edit shows as Sai, so "Last edited by" proves nothing.
2. Apply only to rows with `Submit? = Yes` AND `Approved at` set AND Status Drafted.
3. Never invent a form answer: rules come from "Form Answers v2" on the memory page; `ASK`
   and unknown required questions block that job (write the question into Notes).
4. Resume content follows the memory page's "Resume decisions" (latest date wins). Still fixed:
   employers, titles, dates, degrees, every number; never claim clearance or citizenship.
5. Tsenta: at most 15 applications a day, keep 30 credits in reserve, never change Tsenta
   settings or the Tsenta profile. Our filler (Greenhouse/Lever/Ashby) has no credit limit.
6. No scraping of LinkedIn or Indeed pages. Indeed jobs come from the Indeed connector; their
   apply links can't be followed automatically, so find the same job on the employer's
   board or route it to Sai.
7. Two failures on the same thing → stop, note "LEFT after 2 failures: <reason>", move on.
8. One email everywhere: saitejakoppolu24@gmail.com.

## 0. Setup
```bash
cd /home/user/job-search
git fetch -q origin claude/vigilant-feynman-x99oem && git checkout -q claude/vigilant-feynman-x99oem && git pull -q
cd projects/auto-apply
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
mkdir -p runs/v2
```
Fill `runs/` (git-ignored, never commit it):
- `runs/answers.json` ← the JSON block under **Form Answers v2** on the memory page
- `runs/profile_raw.json` ← Tsenta `get-resume-profile` (default) →
  `.venv/bin/python -m auto_apply.cli profile runs/profile_raw.json --set diversityEquityInclusion.gender=Male --set personalInformation.email=saitejakoppolu24@gmail.com`
- `runs/instructions.txt` ← empty file

## 1. Outcome sync (every run)
1. Tsenta `list-inbox-messages` for each category ACKNOWLEDGMENT, ASSESSMENT, RECRUITER_MESSAGE,
   INTERVIEW, OFFER, REJECTION with `sinceDays: 7`, all pages. Keep id, from, fromName,
   subject, receivedAt, category, application{companyName, trackedApplication{positionTitle}}
   → `runs/v2/inbox.json`.
2. Read all tracker rows through the all-rows view (page with `start_cursor`). Keep url, Job,
   Company, Status, Notes, Apply URL, Location, Score, date:Date:start → `runs/v2/tracker.json`.
3. `.venv/bin/python -m auto_apply.v2.outcomes --tracker runs/v2/tracker.json --inbox runs/v2/inbox.json --out runs/v2/plan.json`
4. Apply the plan: each update → `update_properties` with the new Status and Notes = old Notes +
   `<br>[v2 outcome sync <date>: <old> -> <new>. Evidence: <date> <category>: <subject>] [outcome:<ids>]`;
   each new row → create it (Job "<Company> - <title>", Status, Submit? No, Date = first email,
   Notes "Added from Tsenta inbox …" with the [outcome:ids]). Unmatched emails: list them in the report.
5. Anything with INTERVIEW, OFFER, RECRUITER_MESSAGE or ASSESSMENT → put "NEEDS SAI:" at the
   start of that row's Notes and list it first in the report.

## 2. Find
- Tsenta `get-job-recommendations`: datePosted "3d", locations country:US, ENTRY_LEVEL, FULL_TIME,
  maxYearsExperience 2, limit 40.
- Indeed `search_jobs` (country US, fulltime) for each of "data analyst", "business analyst",
  "reporting analyst", "business intelligence analyst" × locations "Memphis, TN", "remote",
  "Atlanta, GA", "Birmingham, AL". Use `get_job_details` only for jobs that survive step 3.
- Write every job as {title, company, location, posted, url, source, ats, score?} to `runs/v2/jobs.json`.

## 3. Dedupe and target
1. Drop jobs already in the tracker (company + similar title, or same Apply URL), whatever
   their Status, including "Added from Tsenta inbox" rows and Sai's manual ones.
2. `.venv/bin/python -m auto_apply.v2.target runs/v2/jobs.json --out runs/v2/ranked.json`
   keeps entry-level analyst titles posted within 72 hours and orders them
   Memphis > Remote > Atlanta > Alabama > rest of US, then score.
3. Read each kept job's full description (Tsenta `get-job-details` / Indeed `get_job_details`).
   Skip and note: citizens only, clearance, more than 4 years required, degree we don't have,
   language not spoken, the hiring area excludes Tennessee (e.g. "TX, FL, GA residents only").
4. Take the top 8 (DRY_RUN: top 3).

## 4. Build and check each resume
1. Build with the **sai-resume-tailor** skill from the posting.
2. `.venv/bin/python -m auto_apply.v2.ats_check <pdf> --email saitejakoppolu24@gmail.com --phone "+1 901-343-7273"`
   must PASS. A FAIL means fix the LaTeX (plain-hyphen dates, the email above) and rebuild.
3. **AI screen, batched** (ONE fresh-context subagent for all of this run's resumes; each
   subagent costs ~60k tokens of startup overhead, so never one per resume): give it ONLY the
   posting texts and the PDFs' extracted texts, paired by file name, and the screener prompt in
   the resume skill's `references/ai-screen.md`. For each resume it returns a score, advance or
   reject, and the 3 strongest reasons to reject.
   Fix each in the resume, or accept it and write it under "Gaps" in Notes. Never invent
   anything to fix a reason. Builders do not red-team their own resumes; after the batched
   review, apply all fixes in one pass (no separate fixer subagent per resume).
4. If the job's form is on Greenhouse, Lever or Ashby: `.venv/bin/python -m auto_apply.filler.cli plan <url> --pdf <pdf>`;
   open questions land in `questions.json` next to the PDF. Draft job-specific answers from the
   facts only into `answers.json` there; put the drafts in Notes as "Drafted answers — approve?".

## 5. Add rows for Sai
For each built job create a tracker row: Job, Company, Location, Date (today), Apply URL,
Source URL, Score, Status **Drafted**, Submit? **No**, and Notes: location tier, why it fits,
gaps (including red-team reasons accepted), how it will be sent (filler or Tsenta or manual),
drafted answers. Attach the resume (memory page Workflow step 5: Tsenta request-resume-upload
→ PUT → check-custom-resume → Notion create-attachment with source_url = viewUrl → Resume).
Sai approves on the review page.

## 6. Apply approved rows (skip in DRY_RUN)
Rows from the review-queue view with Submit? = Yes AND Approved at set:
1. Still open? If not: Status Skipped, note why.
2. Download the row's attached PDF. Run `ats_check` again; FAIL → note and skip.
3. `.venv/bin/python -m auto_apply.cli gate <pdf> --url <apply url>` (duplicates and daily cap).
4. Route: Greenhouse / Lever / Ashby → `.venv/bin/python -m auto_apply.filler.cli fill <url> --pdf <pdf> --submit`
   (exit 3 = blocked on answers → NEEDS SAI note; captcha or NOT SUBMITTED → NEEDS SAI note with the link).
   Everything else → Tsenta `request-resume-upload` → `cli upload` → `check-custom-resume` →
   `apply-with-custom-resume` (never `apply-to-job`).
5. Record: Status Applied (or Waiting for a queued Tsenta application), Notes "Sent via <route> <time>".

## 7. Report (5–8 lines, also appended to the memory page Run Log)
NEEDS SAI items first, then: outcomes synced (updates / new rows / unmatched), jobs found →
kept → built, applications sent by route, Tsenta credits left, anything that failed twice.

**Token log (every run, last line of the Run Log entry).** Each subagent's completion notice
reports its `subagent_tokens`; keep a running tally by stage while the run goes, and write:
`Tokens (subagents): sync <n> · find <n> · screen <n> · build <n> · review <n> · fix <n> · total <n> · per resume <total/resumes built> · agents <count>`
Use 0 for a stage that ran in the main thread, and say "main thread not counted". This is the
baseline for comparing runs (the v2 real run on 2026-10-19 used 1,394,323 subagent tokens for
6 resumes, ~162k per resume build+review+fix, before review batching).
