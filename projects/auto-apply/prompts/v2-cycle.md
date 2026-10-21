# Job agent v2: one run

Goal: **a callback from a person.** Fewer, better-aimed applications: entry-level analyst roles,
Sai's locations first, fresh postings, a checked resume, and nothing sent without Sai's approval.

Read first, every run: the Notion memory page `3f755fb9-8924-81a1-b4c8-fe6cc3265094`
(decisions there are Sai's and override this file), then this file.

**Mode:** if the message that started this run says `DRY_RUN`, do steps 0–5 and 7, build at
most 3 resumes, and send nothing (skip step 6).

**No Tsenta (Sai, 2026-10-21).** Tsenta is out of the workflow: outcomes come from Gmail, jobs
from the Indeed connector and company career boards, resume files go straight to Notion, and
applications go through our cloud filler (Greenhouse, Lever, Ashby) or Sai's Chrome autofill
extension (everything else), with Claude driving Sai's Chrome as the fallback.

## Fixed IDs
- Tracker data source: `collection://3957830f-6f7e-46ae-8109-a5845caa5ef2`
- Views (use these to READ the tracker; they don't count against Notion's query allowance):
  all rows `view://3fe55fb9-8924-818f-b009-000c503e0b57`, review queue `view://3fe55fb9-8924-811d-b461-000cabb1075f`.
  Do not use SQL or rows-mode queries on the tracker: the plan's allowance runs out.
- Sai's review page: https://claude.ai/artifact/Kww5m3d7yNZZMvbSELseF9
- Resume Knowledge Base Profile page (application profile, title variants): `3fe55fb9-8924-817d-a3c1-f84558b1d4c2`

## Hard rules
1. **Never set `Submit?` or `Approved at`, and never revert them.** Only Sai's review page writes
   them. Every Notion edit shows as Sai, so "Last edited by" proves nothing.
2. Apply only to rows with `Submit? = Yes` AND `Approved at` set AND Status Drafted.
3. Never invent a form answer: rules come from "Form Answers v2" on the memory page; `ASK`
   and unknown required questions block that job (write the question into Notes).
4. Resume content comes from the Resume Knowledge Base as its "Where each resume section is
   written from" section says, and follows the memory page's "Resume decisions" (latest date
   wins). Still fixed: employers, titles, dates, degrees, every number; never claim clearance,
   citizenship, licenses or extra years.
5. At most 15 applications a day across all routes.
6. No scraping of LinkedIn or Indeed pages. Indeed jobs come from the Indeed connector; their
   apply links can't be followed automatically, so find the same job on the employer's
   board or route it to Sai.
7. Two failures on the same thing → stop, note "LEFT after 2 failures: <reason>", move on.
8. One email everywhere: saiteja.koppolu01@gmail.com (memory page, "One email everywhere").

## 0. Setup
```bash
cd /home/user/job-search 2>/dev/null || git clone -q https://github.com/kstc707/job-search /home/user/job-search && cd /home/user/job-search
git fetch -q origin claude/vigilant-bohr-vawl21 && git checkout -q claude/vigilant-bohr-vawl21 && git pull -q
cd projects/auto-apply
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
mkdir -p runs/v2
```
Fill `runs/` (git-ignored, never commit it):
- `runs/answers.json` ← the JSON block under **Form Answers v2** on the memory page
- `runs/profile.json` ← the JSON block under **Application profile** on the Profile page
- `runs/never_claim.txt` ← one line: `clearance, citizenship` (the tool list is lifted, see rule 4)
- `runs/instructions.txt` ← empty file
- `runs/titles.json` ← the JSON block under **Title variants by posting** on the Profile page
- `runs/profile-pack.json` ← `.venv/bin/python -m auto_apply.fillpack profile --profile runs/profile.json --answers runs/answers.json --out runs/profile-pack.json`
  (Sai loads this once into the Chrome extension; rebuild and re-attach it to the memory page
  when the profile or answers change)

## 1. Outcome sync (every run)
1. Gmail `search_threads` for the last 7 days with
   `newer_than:7d (application OR applying OR applied OR interview OR assessment OR "thank you for your interest" OR "next steps")`,
   then `get_thread` for each hit; save the messages as returned → `runs/v2/gmail.json`.
2. `.venv/bin/python -m auto_apply.v2.gmail_inbox runs/v2/gmail.json --out runs/v2/inbox.json`
   classifies each email (ACKNOWLEDGMENT, REJECTION, INTERVIEW, ASSESSMENT, RECRUITER_MESSAGE,
   OFFER) and extracts company and title.
3. Read all tracker rows through the all-rows view (page with `start_cursor`). Keep url, Job,
   Company, Status, Notes, Apply URL, Source URL, Location, Score, date:Date:start → `runs/v2/tracker.json`.
4. `.venv/bin/python -m auto_apply.v2.outcomes --tracker runs/v2/tracker.json --inbox runs/v2/inbox.json --out runs/v2/plan.json`
5. Apply the plan: each update → `update_properties` with the new Status and Notes = old Notes +
   `<br>[v2 outcome sync <date>: <old> -> <new>. Evidence: <date> <category>: <subject>] [outcome:<ids>]`;
   each new row → create it (Job "<Company> - <title>", Status, Submit? No, Date = first email,
   Notes "Added from Gmail …" with the [outcome:ids]). Unmatched emails: list them in the report.
6. Anything with INTERVIEW, OFFER, RECRUITER_MESSAGE or ASSESSMENT → put "NEEDS SAI:" at the
   start of that row's Notes and list it first in the report.
Replies to applications sent before 2026-10-21 may arrive at older addresses the connector does
not read; say so in the report when a row has been Applied for 30+ days with no email at all.

## 2. Find
- Company career boards: `.venv/bin/python -m auto_apply.v2.boards prompts/watchlist.example.json --out runs/v2/boards.json`
  (Greenhouse, Lever and Ashby public job APIs for the watchlist companies; full descriptions included).
- Indeed `search_jobs` (country US, fulltime) for each of "data analyst", "business analyst",
  "reporting analyst", "business intelligence analyst" × locations "Memphis, TN", "remote",
  "Atlanta, GA", "Birmingham, AL". Use `get_job_details` only for jobs that survive step 3.
- Write every job as {title, company, location, posted, url, source, ats, score?} to `runs/v2/jobs.json`.

## 3. Dedupe and target
1. `.venv/bin/python -m auto_apply.v2.dedupe runs/v2/jobs.json --tracker runs/v2/tracker.json --out runs/v2/deduped.json`
   drops anything already in the tracker, whatever its Status (same posting, same requisition
   id, repost or another board, 60-day company cooldown). Only KEEP jobs go on.
2. `.venv/bin/python -m auto_apply.v2.target runs/v2/deduped.json --out runs/v2/ranked.json`
   keeps entry-level analyst titles posted within 72 hours and orders them
   Memphis > Remote > Atlanta > Alabama > rest of US, then score.
3. Read each kept job's full description (board description, or Indeed `get_job_details`).
   Skip and note: citizens only, clearance, more than 4 years required, degree we don't have,
   language not spoken, the hiring area excludes Tennessee (e.g. "TX, FL, GA residents only").
4. Take the top 8 (DRY_RUN: top 3).

## 4. Build and check each resume
1. `.venv/bin/python -m auto_apply.v2.titles choose "<posting title>"` gives the title for each
   job (Data Analyst Intern is fixed; other roles may add a focus, e.g. "Data Analyst (Business
   Intelligence)"). Build with the **sai-resume-tailor** skill from the posting, using exactly
   those titles, then `.venv/bin/python -m auto_apply.v2.titles check <pdf> --posting-title "<posting title>"`
   must PASS.
2. `.venv/bin/python -m auto_apply.v2.ats_check <pdf> --email saiteja.koppolu01@gmail.com --phone "+1 901-343-7273"`
   must PASS. A FAIL means fix the LaTeX (plain-hyphen dates, the email above) and rebuild.
3. **Red-team review, batched** (ONE fresh-context subagent for all of this run's resumes; each
   subagent costs ~60k tokens of startup overhead, so never one per resume): give it ONLY the
   posting texts and the PDFs' extracted texts, paired by file name. Its job: a recruiter with 200
   applicants who wants to reject. For each resume it names the 3 strongest reasons to say no.
   Fix each in the resume, or accept it and write it under "Gaps" in Notes. Never invent
   anything to fix a reason. Builders do not red-team their own resumes; after the batched
   review, apply all fixes in one pass (no separate fixer subagent per resume).
4. Form questions:
   - Greenhouse, Lever or Ashby: `.venv/bin/python -m auto_apply.filler.cli plan <url> --pdf <pdf>`;
     open questions land in `questions.json` next to the PDF.
   - Any other ATS: the questions are only visible inside the form, so the extension reports
     them when Sai fills it; nothing to draft now.
   Draft job-specific answers from the facts only into `answers.json` next to the PDF; put the
   drafts in Notes as "Drafted answers — approve?".
5. Job pack for the extension (every job): `.venv/bin/python -m auto_apply.fillpack job --pdf <pdf> --url <apply url> --title "<title>" --company "<company>" [--answers <job>/answers.json] --out <job>/job-pack.json`.

## 5. Add rows for Sai
For each built job create a tracker row: Job, Company, Location, Date (today), Apply URL,
Source URL, Score, Status **Drafted**, Submit? **No**, and Notes: location tier, why it fits,
gaps (including red-team reasons accepted), route (**filler** for Greenhouse/Lever/Ashby,
**extension** for everything else), drafted answers.
Attach files straight from disk (no Tsenta, no retyping file contents):
1. Notion `create-file-upload` with the filename (e.g. `SaiTejaKoppolu_<Company>_<Role>.pdf`).
2. POST the file to the returned `upload_url` with every returned header:
   `curl -sS -X POST "<upload_url>" -H "authorization: <value>" -F "file=@<pdf>;filename=<filename>;type=application/pdf"`
   and check the response says `"status":"uploaded"`.
3. `update_properties` on the row: `"Resume": [{"type":"file_upload","file_upload":{"id":"<file_upload_id>"}}]`.
Upload `job-pack.json` the same way and add it to the row's page body as a file block, so Sai
can download it from the row. Sai approves on the review page.

## 6. Apply approved rows (skip in DRY_RUN)
Rows from the review-queue view with Submit? = Yes AND Approved at set:
1. Still open? If not: Status Skipped, note why.
2. Download the row's attached PDF. Run `ats_check` again; FAIL → note and skip.
3. `.venv/bin/python -m auto_apply.cli gate <pdf> --url <apply url>` (duplicates and daily cap).
4. Route by ATS:
   - **Greenhouse / Lever / Ashby (filler, cloud):** `.venv/bin/python -m auto_apply.filler.cli fill <url> --pdf <pdf> --submit`
     (exit 3 = blocked on answers → NEEDS SAI note; captcha or NOT SUBMITTED → route to the extension).
   - **Everything else (extension, Sai's Chrome):** Status stays Drafted; Notes gets
     `NEEDS SAI: apply with the extension: open <apply url>, load the job pack from this row,
     click Fill this page on each step, check, Submit. Then set Status Applied.` Sai submits.
   - **Fallback, Claude drives Chrome:** when Sai has written "extension failed" (or "use chrome")
     in a row's Notes, and Claude in Chrome or the linked-computer browser tools are available in
     this session, read the `chrome-browser` (or `built-in-browser`) skill first, open the apply URL
     in a new tab of Sai's Chrome, fill from `runs/profile.json`, `runs/answers.json` and the
     job's answers, upload the job's PDF, and stop on the final review page with a screenshot in
     the report: Sai clicks Submit. Account creation, email verification and captchas are Sai's.
     Without those tools, leave the NEEDS SAI note.
5. Record: Status Applied (filler) with Notes "Sent via filler <time>"; for the extension and
   Chrome routes Sai sets Applied, and the next outcome sync confirms it from the acknowledgment email.

## 7. Report (5–8 lines, also appended to the memory page Run Log)
NEEDS SAI items first (including every row waiting for the extension), then: outcomes synced
(updates / new rows / unmatched), jobs found → kept → built, applications by route (filler sent,
extension waiting, Chrome filled), anything that failed twice.

**Token log (every run, last line of the Run Log entry).** Each subagent's completion notice
reports its `subagent_tokens`; keep a running tally by stage while the run goes, and write:
`Tokens (subagents): sync <n> · find <n> · screen <n> · build <n> · review <n> · fix <n> · total <n> · per resume <total/resumes built> · agents <count>`
Use 0 for a stage that ran in the main thread, and say "main thread not counted". This is the
baseline for comparing runs (the v2 real run on 2026-10-19 used 1,394,323 subagent tokens for
6 resumes, ~162k per resume build+review+fix, before review batching).
