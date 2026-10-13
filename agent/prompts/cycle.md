# Job-search agent: one cycle

Placeholders in braces are filled in the scheduled trigger's prompt, not stored here.
`{CONFIG}` is the person's config JSON (see `config.example.json`): their limits, thresholds,
feed filter and daily cap. Nothing personal is stored in this repo.

## Where everything lives (one Google Sheet `{SHEET}` + resumes on the person's computer)

| Tab | Columns | Who writes it |
|---|---|---|
| `Tracker` | A Job, B Company, C Location, D Status, E Submit?, F Score, G Date, H Apply URL, I Resume (link), J Notes | agent; the person only sets E |
| `State` | Item, Value | agent rewrites it at the end of every run; read it first |
| `Memory` | Section, Rule or fact, Set by | decisions, selection rules, lessons, QC rules, open questions |
| `Run Log` | Run, Date, What happened, Credits after | one row appended per run |
| `Failures` | Employer, Job, ATS, Failure, Count, Action, Last seen, Detail | two-strike ledger |
| `Gaps` | Gap, Jobs, Share, Do not claim, How to close it, Updated | refreshed from `jobagent gaps` |
| `Bullets` | Bullet id, Family, Text, Uses, Successes, Rate | filled at the first interview or offer |

Write rules (every write can need approval, so keep them few):
- Read with ranges, not cell by cell: one `get_values` per tab you need.
- New rows: ONE `append_values` to `Tracker!A:J` per run, after the resumes are uploaded.
- Status changes: ONE `update_values` per contiguous block; when several rows change, rewrite the
  `Tracker!D2:E<last>` block in one call instead of one call per row.
- Logs and ledgers: one `append_values` each.

## 0. Gate (always first, keep it cheap)
One `get_values Tracker!A:J`. Work exists if any row has: Submit? = Yes and Status in (Drafted,
Approved, empty); Status = Drafted and no Resume link; Status = Waiting.
If none, and the `State` tab says the last scout was today (Central time), reply `nothing to do`
and stop.

## 1. Read state, not history
`get_values State!A:B` and `Memory!A:C`. Do not reread old conversation to rebuild state.

## 2. Track
- For every Waiting row, read the Tsenta application status. Sent -> Applied. Failed -> append to
  `Failures`; second failure for the same employer + ATS -> Submit? = No and Notes
  `LEFT after 2 failures: <reason>`.
- `list-inbox-messages` since the last run: REJECTION -> Status Rejected; INTERVIEW / OFFER ->
  Interview Scheduled / Offer; ASSESSMENT or needsReply -> add to `State` under "Manual for <name>".
- Interview or offer -> bullet scan: download each sent resume PDF from its link to `work/sent/<row>.pdf`,
  run `python -m jobagent bullets scan work/sent --success <apps> --families <app=family,...>
  --out LIB.json`, append its bullets to `Bullets`.

## 3. Apply (Submit? = Yes rows only)
Check the posting is still open. Tsenta `request-resume-upload`, `curl -X PUT` the row's PDF
(the local build, or download it from the row's link), `check-custom-resume`, then
`apply-with-custom-resume`. The linked PDF is the record of what was sent. Status -> Waiting,
then Applied once Tsenta reports it sent.

## 4. Scout and score (once a day, at most `daily_cap` jobs, default 15)
Tsenta recommendations, filtered at the source with the config's `feed_query` (title terms in
`search`, senior/intern/clearance words in `excludeSearch`, `maxYearsExperience`, `jobTypes`) so
only matching titles reach the JD read; then web search for the same targets. Save each job
description to `jds/<slug>.md`: a JSON header with the feed fields (`title`, `companyName`,
`locations`, `yearsOfExperienceMin`, `degreeRequirements`, `sponsorship`, `clearanceRequired`,
`datePosted`), a blank line, then the posting text. Skip anything already in `Tracker`.
Run the pre-build gate (no model tokens):

    python -m jobagent rank jds/*.md --config {CONFIG} --facts <facts.md>

It drops knockouts (citizenship, clearance, sponsorship when needed, too many years, degree, senior
title, student-only) and anything under `thresholds.build`, and returns the rest best first, capped.

## 5. Build, audit, score, upload
- Builders: half as many as jobs to build, rounded up (2 jobs each), all launched at once, using
  the resume skill. Bullet wording may repeat an earlier resume only if
  `python -m jobagent bullets reusable LIB.json --family <ai|ds|da>` lists it.
- Every PDF must pass, re-run in the main session after all builders finish:

      python -m jobagent audit <tex> --facts <facts.md> --example <example.tex> \
          --pdf <pdf> --jd-map <jd_map.md> --others <resumes dir> --approved LIB.json

- Score each finished resume:

      python -m jobagent score jds/<slug>.md --config {CONFIG} --facts <facts.md> \
          --jd-map <jd_map.md> --tex <tex> --pdf <pdf> [--signal 0-1]

- Resume store: the person's own computer. Send each run's passing PDFs to them in ONE
  `SendUserFile` call (display `attach`, status `proactive`) so they save them to their resumes
  folder; column I holds the file name. Keep the build in `work/resumes/` too: step 3 applies with
  that local copy. If it is gone (container reset), rebuild from the .tex or ask for the saved PDF.
  When a session runs on the person's computer (desktop app or `claude remote-control`), write the
  PDF straight into their folder instead. Never send a PDF as base64 through a tool argument.
- Then ONE `append_values` to `Tracker` with every new row: Status Drafted, Score, Resume link,
  Notes (gaps, flags). `auto` (score >= thresholds.auto) rows get Submit? = Yes and are applied in
  step 3 of the next run; `review` rows leave Submit? empty for the person; `skip` rows are not added.

## 6. Update state
Rewrite `State` (one `update_values`), append one `Run Log` row, append new `Failures`, and refresh
`Gaps` from `python -m jobagent gaps <all jd_map.md>`.

## 7. Reply in 5-8 lines.
